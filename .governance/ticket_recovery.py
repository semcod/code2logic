#!/usr/bin/env python3
"""Bounded local allocator recovery; never a protected approval mechanism.

The trusted local caller supplies the existing external controller store. Its
lock is held throughout observation and materialization. We neither create a
controller store nor acquire/renew/reclaim leases. Multi-node and SQLite ticket
allocation must use their own registered recovery controller instead.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlparse

sys.dont_write_bytecode = True
from governance_check import pattern_covered_by, validate_intent_value
import work_start_check as start
from ticket_allocation import canonical_repository_ref

FIELDS = {"schema", "intent", "headSha", "dirtyDigest", "leaseId",
          "leaseRevision", "fencingToken", "ownerActor", "ownerSession"}


class RecoveryError(ValueError):
    """Safe fixed diagnostic; candidate/controller data is never interpolated."""


def require(condition, message):
    if not condition:
        raise RecoveryError(message)


def safe_path(path):
    path = Path(os.path.abspath(path))
    require(all(not p.is_symlink() for p in (path, *path.parents)), "Symlinked recovery path")
    return path


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    descriptor = os.open(safe_path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Regular file required")
        raw = stream.read(4 * 1024 * 1024 + 1)
    require(len(raw) <= 4 * 1024 * 1024, "Recovery input too large")
    return json.loads(raw, object_pairs_hook=unique)


@contextmanager
def controller_lock(store):
    # POSIX controller adapter, fail closed on platforms without flock.
    import fcntl
    path = safe_path(store / ".lock")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode), "Controller lock must be a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def validate_lease(store, request, intent, repository, branch, worktree):
    state = load(store / "state.json")
    require(state.get("schema") == "subactor.repository-change-lease-store/v1", "Unsupported controller store")
    lease = state["leases"][request["leaseId"]]
    expected = {
        "schema": "wellmanifest.change-lease/v1", "leaseId": request["leaseId"],
        "leaseRevision": request["leaseRevision"], "fencingToken": request["fencingToken"],
        "ownerActor": request["ownerActor"], "ownerSession": request["ownerSession"],
        "repositoryRef": repository, "ticketId": intent["ticket"],
        "targetBranch": intent["delivery"]["targetBranch"], "branchRef": branch,
        "workstream": intent["workstream"], "worktreeId": worktree,
        "scopeHash": start.digest(intent["allowedPaths"]), "phase": "editing",
        "publicationFrozen": False,
    }
    require(all(lease.get(k) == v for k, v in expected.items()), "Controller owner, scope or CAS mismatch")
    resource = start.digest({"repositoryRef": repository, "targetBranch": expected["targetBranch"]})
    require(state["active"].get(resource) == lease["leaseId"], "Lease is not the active controller owner")
    expires = datetime.fromisoformat(lease["expiresAt"].replace("Z", "+00:00"))
    require(expires.tzinfo is not None and expires > datetime.now(timezone.utc), "Expired lease; explicit controller handoff required")
    return lease


def inspect_recovery(root, request, workstream):
    require(isinstance(request, dict) and set(request) == FIELDS
            and request["schema"] == "new-project.ticket-recovery-request/v1", "Invalid recovery request")
    for field in ("headSha", "dirtyDigest"):
        require(isinstance(request[field], str) and re.fullmatch(
            r"[0-9a-f]{40}" if field == "headSha" else r"[0-9a-f]{64}", request[field]), "Invalid exact-state binding")
    for field in ("leaseRevision", "fencingToken"):
        require(type(request[field]) is int and request[field] > 0, "Positive integer CAS required")
    for field in ("leaseId", "ownerActor", "ownerSession"):
        require(isinstance(request[field], str) and 0 < len(request[field]) <= 255, "Explicit owner required")
    intent = request["intent"]
    require(isinstance(intent, dict), "Bounded intent required")
    _, error = validate_intent_value(intent, intent.get("ticket", ""))
    require(error is None, "Invalid bounded intent")
    require(intent.get("schema") == "new-project.intent/v3" and "delivery" in intent,
            "Complete v3 delivery intent required")
    require(not any(ord(c) < 32 for c in intent["summary"]), "Single-line ticket summary required")
    require(intent["workstream"] == workstream, "Workstream mismatch")
    ticket = intent["ticket"]
    require(re.fullmatch(r"ticket-[0-9]{3,}", ticket), "Invalid ticket identity")
    branch = start.git(root, "symbolic-ref", "HEAD").strip()
    match = re.fullmatch(r"refs/heads/ticket/" + ticket[7:] + r"-([a-z0-9]+(?:-[a-z0-9]+)*)", branch)
    require(match is not None, "Recovery requires the existing matching ticket branch")
    registrations = start.worktrees(root)
    primary = safe_path(registrations[0]["worktree"])
    require(root == primary / ".worktrees" / (ticket + "--" + match[1]), "Noncanonical recovery checkout")
    gitdir = Path(start.git(root, "rev-parse", "--absolute-git-dir").strip())
    backlink = (gitdir / "gitdir").read_text().strip()
    require(not Path(backlink).is_absolute(), "Relative worktree registration required")
    require(not (root / "project" / ticket).exists(), "Existing ticket must be continued, not imported")
    require(start.git(root, "rev-parse", "HEAD").strip() == request["headSha"], "HEAD changed")
    report = start.inspect(root, workstream, ticket=ticket, storage="files",
                           expected_dirty_digest=request["dirtyDigest"], recovery_intent=intent)
    require(report["route"] == "REUSE_EXISTING" and report["activeTicketCount"] <= report["workstreamLimit"],
            "Recovery admission contested or WIP exceeded")
    selected = next(e for e in report["worktrees"] if e["path"] == str(root))
    require(selected["active"], "Terminal identity cannot be recovered as active work")
    require(selected["dirtyDigest"] == request["dirtyDigest"], "Dirty state changed")
    base = intent["delivery"]["acceptedBaseSha"]
    require(start.git(root, "merge-base", base, request["headSha"]).strip() == base, "Accepted base is not an ancestor")
    paths = set(start.git(root, "diff", "--name-only", "--no-renames", "-z", base, request["headSha"]).split("\0")) - {""}
    paths.update(selected["allDirtyPaths"])
    allowed = tuple(start.patterns(intent["allowedPaths"]))
    forbidden = tuple(intent["forbiddenPaths"])
    owned = tuple(start.manifest_at(root)["coordination"]["workstreams"][workstream]["ownedPaths"])
    require(all(any(pattern_covered_by(pattern, owner) for owner in owned)
                for pattern in start.material(list(allowed))),
            "Declared recovery scope exceeds workstream ownership")
    require(all(start.path_ignored(p, owned) for p in start.material(list(paths))),
            "Existing work exceeds workstream ownership")
    require(all(start.path_ignored(p, allowed) and not start.path_ignored(p, forbidden) for p in paths),
            "Existing work exceeds accepted recovery scope")
    own = f"project/{ticket}/"
    require(all(start.path_ignored(own + name, allowed) and not start.path_ignored(own + name, forbidden)
                for name in ("README.md", "intent.json")), "Recovery carriers outside scope")
    # A branch spelling is not a ticket reservation. Never duplicate an identity
    # found in another checkout, ref, SQLite store, or the clone high-water mark.
    require(not (primary / "project.sqlite").exists(), "SQLite identity requires its registered adapter")
    for entry in registrations:
        require(not (safe_path(entry["worktree"]) / "project" / ticket).exists(), "Ticket already exists in a checkout")
    refs = start.git(root, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").splitlines()
    origin_alias = "refs/remotes/origin/" + branch.removeprefix("refs/heads/")
    for ref in refs:
        require(not start.git(root, "ls-tree", "--name-only", ref, own.rstrip("/")).strip(), "Ticket already exists in Git history")
        name = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref.split("/", 3)[-1]
        other = start.TICKET.fullmatch(name)
        same_published_branch = (ref == origin_alias
                                 and start.git(root, "rev-parse", ref).strip() == request["headSha"])
        require(not other or other[1] != ticket[7:] or ref == branch or same_published_branch,
                "Ticket branch collision")
    require(report["targetBranch"] == intent["delivery"]["targetBranch"], "Target branch mismatch")
    return intent, report, primary, branch


def recover(root, request_path, store, workstream):
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX local controller adapter required")
    root, store, request_path = map(safe_path, (root, store, request_path))
    root = safe_path(start.git(root, "rev-parse", "--show-toplevel").strip())
    common = safe_path(start.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    require(start.configured_mode(root) == "files", "Recovery only supports file tickets")
    policies = [root / ".governance/ticket-allocation.json", root / "governance/ticket-allocation.json"]
    policy = next((p for p in policies if p.exists()), None)
    if policy:
        from ticket_allocation import parse_config
        require(parse_config(policy)["mode"] == "local-single-clone", "Registered allocation requires its controller adapter")
    for location in start.worktrees(root):
        checkout = safe_path(location["worktree"])
        require(not store.is_relative_to(checkout) and not request_path.is_relative_to(checkout),
                "Controller and request must be outside all candidate checkouts")
    require(not store.is_relative_to(common), "Controller cannot be stored in candidate Git metadata")
    lock = safe_path(common / "new-project-ticket-allocation.lock")
    lock.mkdir()  # same non-stealable clone lock as ordinary allocation
    try:
        with controller_lock(store):
            request = load(request_path)
            intent, report, primary, branch = inspect_recovery(root, request, workstream)
            origin = urlparse(canonical_repository_ref(start.git(root, "config", "--get", "remote.origin.url").strip()))
            require(origin.hostname == "github.com" and origin.scheme in {"https", "git+ssh"},
                    "This controller adapter requires a canonical GitHub repository")
            repository = origin.path.lstrip("/")
            lease = validate_lease(store, request, intent, repository, branch, root.name)
            number = int(intent["ticket"][7:])
            highwater = safe_path(common / "new-project-ticket-high-water")
            previous = highwater.read_text().strip() if highwater.exists() else "0"
            require(re.fullmatch(r"[0-9]+", previous) and number > int(previous), "Identity already reserved; preserve and reconcile")
            # Observe again while controller ownership cannot transition. No Git
            # state, lease or existing source file is ever rewritten by recovery.
            _, refreshed, _, _ = inspect_recovery(root, request, workstream)
            require(refreshed["observationDigest"] == report["observationDigest"], "Workspace observation changed")
            validate_lease(store, request, intent, repository, branch, root.name)
            temporary = common / "new-project-ticket-high-water.recovery"
            with temporary.open("x") as stream:
                stream.write(str(number) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, highwater)
            directory = safe_path(root / "project" / intent["ticket"])
            directory.mkdir()  # crash/partial recovery remains reserved, never overwritten
            readme = (f"# {intent['ticket']}: {intent['summary']}\n\n"
                      "- **Status**: IN_PROGRESS\n- **Workflow state**: EDIT\n\n"
                      "## Recovery boundary\n\n"
                      "Existing work registered through the fenced local allocator.\n"
                      "This is not retrospective validation or protected merge approval.\n")
            criteria = sorted({item["criterion"] for item in intent["delivery"]["validation"]})
            readme += "\n## Acceptance criteria\n\n" + "".join(
                f"- [ ] {criterion}: Validate the corresponding accepted intent criterion.\n" for criterion in criteria)
            for name, content in (("README.md", readme), ("intent.json", json.dumps(intent, indent=2) + "\n")):
                with (directory / name).open("x") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            return {"schema": "new-project.ticket-recovery-result/v1", "ticket": intent["ticket"],
                    "headSha": request["headSha"], "leaseId": lease["leaseId"],
                    "leaseRevision": lease["leaseRevision"], "fencingToken": lease["fencingToken"],
                    "requestDigest": start.digest(request), "grantsMergeAuthority": False}
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--lease-store", type=Path, required=True)
    parser.add_argument("--workstream", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(recover(args.root, args.request, args.lease_store, args.workstream)))
        return 0
    except RecoveryError as error:
        print("GOV-TICKET-ALLOCATION-003: " + str(error) + "; preserve work and re-observe before retry.", file=sys.stderr)
        return 5
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        # No controller contents or candidate paths in the shared diagnostic.
        print("GOV-TICKET-ALLOCATION-003: recovery rejected; re-observe exact request, live controller ownership, scope and admission; preserve all work.", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main())
