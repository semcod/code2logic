#!/usr/bin/env python3
"""Restore the checkout of an already reserved ticket; never allocate or approve.

The allocator's reservation record, high-water mark and the external controller
lease stay authoritative. Restoration re-registers the canonical checkout and
writes only the ticket's own README.md and intent.json from a pinned snapshot.
It grants neither source-editing nor merge authority: normal work-start
admission and independent review remain mandatory afterwards.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlparse

sys.dont_write_bytecode = True
from governance_check import validate_intent_value
import ticket_recovery as recovery
import work_start_check as start
from ticket_allocation import canonical_repository_ref

require = recovery.require
safe = recovery.safe_path
FIELDS = {"schema", "ticket", "worktreeId", "headSha", "snapshotPath", "snapshotSha256",
          "leaseId", "leaseRevision", "fencingToken", "ownerActor", "ownerSession"}
METADATA = ("README.md", "intent.json")
RESTORING_PHASES = {"claimed", "editing"}


def validate_request(request, workstream, local=False):
    fields = FIELDS | {"reservationSha256"} if local else FIELDS
    schema = "new-project.local-ticket-restoration-request/v1" if local else "new-project.ticket-restoration-request/v1"
    require(isinstance(request, dict) and set(request) == fields
            and request["schema"] == schema, "Invalid restoration request")
    if local:
        require(isinstance(request["reservationSha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", request["reservationSha256"]), "Invalid reservation digest")
    ticket = request["ticket"]
    require(isinstance(ticket, str) and re.fullmatch(r"ticket-[0-9]{3,}", ticket), "Invalid ticket identity")
    require(isinstance(request["worktreeId"], str) and re.fullmatch(
        re.escape(ticket) + r"--[a-z0-9]+(?:-[a-z0-9]+)*", request["worktreeId"]), "Noncanonical worktree identity")
    require(request["headSha"] is None or (isinstance(request["headSha"], str)
            and re.fullmatch(r"[0-9a-f]{40}", request["headSha"])), "Invalid exact-head binding")
    require(isinstance(request["snapshotSha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", request["snapshotSha256"]), "Invalid snapshot digest")
    require(isinstance(request["snapshotPath"], str) and Path(request["snapshotPath"]).is_absolute(),
            "Absolute snapshot path required")
    for field in ("leaseRevision", "fencingToken"):
        require(type(request[field]) is int and request[field] > 0, "Positive integer CAS required")
    for field in ("leaseId", "ownerActor", "ownerSession"):
        require(isinstance(request[field], str) and 0 < len(request[field]) <= 255, "Explicit owner required")
    require(isinstance(workstream, str) and workstream, "Workstream required")


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def load_snapshot(request, workstream):
    # Hash and parse the same bytes; the path is never reopened after hashing.
    descriptor = os.open(safe(request["snapshotPath"]), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Regular file required")
        raw = stream.read(4 * 1024 * 1024 + 1)
    require(len(raw) <= 4 * 1024 * 1024, "Snapshot too large")
    require(hashlib.sha256(raw).hexdigest() == request["snapshotSha256"], "Snapshot digest mismatch")
    snapshot = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(snapshot, dict) and set(snapshot) == {"schema", "ticket", "files"}
            and snapshot["schema"] == "new-project.ticket-metadata-snapshot/v1"
            and snapshot["ticket"] == request["ticket"], "Invalid metadata snapshot")
    files = snapshot["files"]
    require(isinstance(files, dict) and set(files) == set(METADATA)
            and all(isinstance(v, str) for v in files.values()), "Snapshot must hold exactly README.md and intent.json")
    intent = json.loads(files["intent.json"], object_pairs_hook=unique)
    _, error = validate_intent_value(intent, request["ticket"])
    require(error is None and intent.get("ticket") == request["ticket"], "Invalid snapshot intent")
    require(intent.get("workstream") == workstream, "Workstream mismatch")
    require(re.search(r"^- \*\*Status\*\*: IN_PROGRESS$", files["README.md"], re.M),
            "Terminal identity cannot be restored as active work")
    return files, intent


def reservation(primary, common, request, workstream):
    number = int(request["ticket"][7:])
    highwater = safe(common / "new-project-ticket-high-water")
    previous = highwater.read_text().strip() if highwater.exists() else "0"
    require(re.fullmatch(r"[0-9]+", previous) and number <= int(previous),
            "Identity is not reserved; allocate normally")
    leases = safe(primary / ".subactor" / "leases")
    matches = [p for p in sorted(leases.glob("ticket-*.json"))
               if p.name.startswith(request["ticket"] + "--")]
    require([p.name for p in matches] == [request["worktreeId"] + ".json"], "Missing or ambiguous reservation")
    record = recovery.load(matches[0])
    slug = request["worktreeId"][len(request["ticket"]) + 2:]
    expected = {"schema": "wellmanifest.change-lease/v1", "ticketId": request["ticket"],
                "worktreeId": request["worktreeId"], "workstream": workstream,
                "branchRef": f"refs/heads/ticket/{request['ticket'][7:]}-{slug}",
                "ownerActor": request["ownerActor"], "ownerSession": request["ownerSession"]}
    require(all(record.get(k) == v for k, v in expected.items()), "Reservation identity or owner mismatch")
    require(isinstance(record.get("headSha"), str) and re.fullmatch(r"[0-9a-f]{40}", record["headSha"]),
            "Reservation base unavailable")
    return record


def controller(store, request, record, intent, repository):
    resource = start.digest({"repositoryRef": repository, "targetBranch": record["targetBranch"]})
    try:
        state = start.read_controller_projection(
            safe(store), resources=(resource,), lease_ids=(request["leaseId"],))
    except (start.ObservationError, OSError, ValueError, KeyError, TypeError) as error:
        raise recovery.RecoveryError("Unsupported or unreadable controller store") from error
    require(state.get("schema") == "subactor.repository-change-lease-store/v1", "Unsupported controller store")
    lease = state["leases"].get(request["leaseId"])
    require(isinstance(lease, dict), "Controller owner, scope or CAS mismatch")
    expected = {"schema": "wellmanifest.change-lease/v1", "leaseId": request["leaseId"],
                "leaseRevision": request["leaseRevision"], "fencingToken": request["fencingToken"],
                "ownerActor": request["ownerActor"], "ownerSession": request["ownerSession"],
                "repositoryRef": repository, "ticketId": request["ticket"],
                "targetBranch": record["targetBranch"], "branchRef": record["branchRef"],
                "workstream": record["workstream"], "worktreeId": request["worktreeId"],
                "scopeHash": start.digest(intent["allowedPaths"]), "publicationFrozen": False}
    require(all(lease.get(k) == v for k, v in expected.items()) and lease.get("phase") in RESTORING_PHASES,
            "Controller owner, scope or CAS mismatch")
    require(state["active"].get(resource) == lease["leaseId"], "Lease is not the active controller owner")
    expires = datetime.fromisoformat(lease["expiresAt"].replace("Z", "+00:00"))
    require(expires.tzinfo is not None and expires > datetime.now(timezone.utc),
            "Expired lease; explicit controller handoff required")
    return lease


@contextmanager
def authority(primary, store, request, record, intent, repository, local_owner):
    """Hold the selected authority lock; never fall back between owner backends."""
    if local_owner is None:
        with recovery.controller_lock(store):
            yield lambda: controller(store, request, record, intent, repository)
        return
    import terminal_lease_release as anchored
    path = primary / ".subactor/leases" / (request["worktreeId"] + ".json")
    with anchored.directory(path.parent) as (fd, verify):
        with anchored.lease_lock(fd, path.name, verify) as verify_lock:
            def check():
                verify_lock()
                raw = anchored.read_at(fd, path.name, private=True)
                info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
                require(info.st_uid == os.geteuid(), "Reservation belongs to another OS owner")
                require(hashlib.sha256(raw).hexdigest() == request["reservationSha256"], "Reservation changed")
                lease = json.loads(raw, object_pairs_hook=unique)
                require(lease == record, "Reservation changed before locking")
                require(not anchored.canonical.validate_lease(lease), "Invalid local lease")
                expected = {key: request[key] for key in
                            ("leaseId", "leaseRevision", "fencingToken", "ownerActor", "ownerSession")}
                expected.update(ticketId=request["ticket"], worktreeId=request["worktreeId"],
                                branchRef=record["branchRef"], targetBranch=record["targetBranch"],
                                workstream=record["workstream"], scopeHash=start.digest(intent["allowedPaths"]))
                require(all(lease.get(k) == v for k, v in expected.items()), "Local owner, scope or CAS mismatch")
                require(tuple(str(request[k]) for k in ("ownerActor", "ownerSession", "leaseRevision", "fencingToken"))
                        == tuple(local_owner), "Explicit current writer identity required")
                legacy = "local/" + hashlib.sha256(str(primary).encode()).hexdigest()
                require(lease["repositoryRef"] in {repository, legacy}, "Local repository mismatch")
                require(lease["phase"] in RESTORING_PHASES and not lease["publicationFrozen"], "Local lease is frozen or inactive")
                issued, heartbeat, expires = (datetime.fromisoformat(lease[k].replace("Z", "+00:00"))
                                               for k in ("issuedAt", "heartbeatAt", "expiresAt"))
                require(all(t.tzinfo is not None for t in (issued, heartbeat, expires))
                        and issued <= heartbeat <= datetime.now(timezone.utc) < expires,
                        "Expired lease; explicit controller handoff required")
                verify_lock()
                return lease
            yield check


def observe(primary, request, record, files, intent):
    """Return the exact current restoration state; reject every collision."""
    ticket, branch = request["ticket"], record["branchRef"]
    canonical = safe(primary / ".worktrees" / request["worktreeId"])
    head = start.git(primary, "rev-parse", "--verify", "--quiet", branch + "^{commit}", optional=True)
    head = head.strip() if head else None
    target = request["headSha"] or record["headSha"]
    require(head in (None, target), "Branch head differs from the bound restoration head")
    require(start.git(primary, "cat-file", "-e", target + "^{commit}", optional=True) is not None,
            "Bound restoration head is unreachable")
    base = record["headSha"]
    require(start.git(primary, "merge-base", "--is-ancestor", base, target, optional=True) is not None,
            "Restoration head does not descend from the reserved base")
    accepted = intent.get("delivery", {}).get("acceptedBaseSha")
    require(accepted is None or start.git(primary, "merge-base", "--is-ancestor", accepted, target,
                                          optional=True) is not None, "Accepted base is not an ancestor")
    registered = None
    for entry in start.worktrees(primary):
        path = safe(entry["worktree"])
        if path == canonical:
            require("prunable" not in entry, "Stale canonical registration; prune it after confirming the loss")
            require(entry.get("branch") == branch, "Canonical checkout registration collides")
            registered = path
            continue
        require(entry.get("branch") != branch, "Ticket branch is checked out elsewhere")
        require(not (path / "project" / ticket).exists(), "Ticket already exists in another checkout")
    refs = start.git(primary, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads").splitlines()
    for name in refs:
        other = start.TICKET.fullmatch(name)
        require(not other or other[1] != ticket[7:] or "refs/heads/" + name == branch, "Ticket branch collision")
    require(registered is not None or not os.path.lexists(canonical), "Unregistered path occupies the checkout")
    committed = bool(start.git(primary, "ls-tree", "--name-only", target, f"project/{ticket}").strip())
    present = {}
    if registered:
        backlink = Path(start.git(canonical, "rev-parse", "--absolute-git-dir").strip()) / "gitdir"
        require(not Path(backlink.read_text().strip()).is_absolute(), "Relative worktree registration required")
        paths = start.dirty_observation(canonical)[2]
        require(all(p.startswith(f"project/{ticket}/") for p in paths), "Restored checkout has foreign changes")
        directory = canonical / "project" / ticket
        require(not directory.is_symlink(), "Symlinked ticket metadata")
        for name in METADATA if not committed else ():
            path = directory / name
            if os.path.lexists(path):
                require(not path.is_symlink() and path.read_text() == files[name],
                        "Existing ticket metadata differs; preserve and continue under normal admission")
                present[name] = True
    return {"canonical": canonical, "branchHead": head, "target": target, "registered": registered is not None,
            "committed": committed, "present": sorted(present)}


def write_new(common, path, content):
    parent = path.parent
    require(not any(p.is_symlink() for p in (parent, *parent.parents)) and parent.is_dir(),
            "Ticket metadata directory must be a non-symlinked directory")
    descriptor, temporary = tempfile.mkstemp(prefix=".new-project-ticket-restore-", dir=parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        require(os.stat(temporary, follow_symlinks=False).st_dev == os.stat(parent, follow_symlinks=False).st_dev,
                "Temporary restoration file must reside on the destination filesystem")
        os.link(temporary, path)  # never replaces an existing file
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def restore(root, request_path, store, workstream, *, local_owner=None):
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX local controller adapter required")
    root, request_path = map(safe, (root, request_path))
    require((store is None) == (local_owner is not None), "Select exactly one restoration authority")
    store = safe(store) if store is not None else None
    common = safe(start.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    primary = safe(start.worktrees(root)[0]["worktree"])
    require(start.configured_mode(primary) == "files" and not (primary / "project.sqlite").exists(),
            "SQLite identity requires its registered adapter")
    policy = next((p for p in (primary / ".governance/ticket-allocation.json",
                               primary / "governance/ticket-allocation.json") if p.exists()), None)
    if policy:
        from ticket_allocation import parse_config
        require(parse_config(policy)["mode"] == "local-single-clone", "Registered allocation requires its controller adapter")
    lock = safe(common / "new-project-ticket-allocation.lock")
    lock.mkdir()  # same non-stealable clone lock as allocation and recovery
    try:
        request = recovery.load(request_path)
        validate_request(request, workstream, local_owner is not None)
        locations = (request_path, safe(request["snapshotPath"])) + ((store,) if store is not None else ())
        for location in start.worktrees(primary):
            checkout = safe(location["worktree"])
            require(not any(p.is_relative_to(checkout) for p in locations),
                    "Controller, request and snapshot must be outside all checkouts")
        require(not any(p.is_relative_to(common) for p in locations), "Recovery inputs cannot reside in Git metadata")
        files, intent = load_snapshot(request, workstream)
        record = reservation(primary, common, request, workstream)
        origin = urlparse(canonical_repository_ref(start.git(primary, "config", "--get", "remote.origin.url").strip()))
        require(origin.hostname == "github.com" and origin.scheme in {"https", "git+ssh"},
                "This controller adapter requires a canonical GitHub repository")
        repository = origin.path.lstrip("/")
        with authority(primary, store, request, record, intent, repository, local_owner) as check:
            lease = check()
            state = observe(primary, request, record, files, intent)
            steps = []
            if state["branchHead"] is None:
                check()
                start.git(primary, "update-ref", record["branchRef"], state["target"], "")  # create-only CAS
                steps.append("branch")
            if not state["registered"]:
                check()
                name = record["branchRef"].removeprefix("refs/heads/")
                start.git(primary, "worktree", "add", "--relative-paths", str(state["canonical"]), name)
                steps.append("checkout")
            state = observe(primary, request, record, files, intent)
            check()
            if not state["committed"]:
                directory = state["canonical"] / "project" / request["ticket"]
                check()
                directory.mkdir(exist_ok=True)
                for name in METADATA:
                    if name not in state["present"]:
                        check()
                        write_new(common, directory / name, files[name])
                        steps.append(name)
            return {"schema": "new-project.ticket-restoration-result/v1", "ticket": request["ticket"],
                    "worktreeId": request["worktreeId"], "branchRef": record["branchRef"],
                    "headSha": state["target"], "outcome": "RESTORED" if steps else "ALREADY_RESTORED",
                    "steps": steps, "metadata": "committed" if state["committed"] else "snapshot",
                    "snapshotSha256": request["snapshotSha256"], "leaseId": lease["leaseId"],
                    "leaseRevision": lease["leaseRevision"], "fencingToken": lease["fencingToken"],
                    "requestDigest": start.digest(request), "grantsEditAuthority": False,
                    "grantsMergeAuthority": False,
                    "nextAction": f"python3 .governance/work_start_check.py --workstream {workstream} "
                                  f"--ticket {request['ticket']}"}
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--lease-store", type=Path)
    backend.add_argument("--local-reservation", action="store_true")
    for name, variable in (("actor", "WRITER_ACTOR"), ("session", "WRITER_SESSION"),
                           ("revision", "LEASE_REVISION"), ("fencing", "FENCING_TOKEN")):
        parser.add_argument("--" + name, default=os.environ.get("NEW_PROJECT_" + variable, ""))
    parser.add_argument("--workstream", required=True)
    args = parser.parse_args()
    try:
        owner = (args.actor, args.session, args.revision, args.fencing) if args.local_reservation else None
        print(json.dumps(restore(args.root, args.request, args.lease_store, args.workstream, local_owner=owner)))
        return 0
    except recovery.RecoveryError as error:
        print("GOV-TICKET-ALLOCATION-003: " + str(error) + "; preserve work and re-observe before retry.", file=sys.stderr)
        return 5
    except (OSError, ValueError, KeyError, TypeError, ImportError, start.ObservationError):
        print("GOV-TICKET-ALLOCATION-003: restoration rejected; re-observe the reservation, snapshot, controller "
              "ownership and registered checkouts; preserve all work.", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main())
