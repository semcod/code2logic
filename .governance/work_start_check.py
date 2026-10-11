#!/usr/bin/env python3
"""Read-only, clone-local work admission. Recommendations never grant authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

sys.dont_write_bytecode = True
from ticket_activity import ActivityError, delivery_landed, resolve as resolve_activity
from ticket_input import configured_mode, load_input, primary_database
from worktree_overlap_check import globs_may_overlap, path_ignored

SCHEMA = "new-project.work-start-report/v1"
CODE = "GOV-WORK-START-001"
TICKET = re.compile(r"^ticket[/-]([0-9]{3,})(?:[-/].*)?$")
TRACKING = ("project/ticket-*/**", "project/TICKETS.md", "TODO.md")


class ObservationError(ValueError):
    pass


def _record_observation_failure(root, error):
    """Write the real exception locally so RECONCILE is self-diagnosable.

    The GOV-WORK-START-001 payload printed to stdout stays deliberately
    generic (remote URLs or secret-bearing input never leak into shared
    CI/agent transcripts). But collapsing every failure — including plain
    bugs like a missing tracked file — into that one sentence made a
    one-line root cause take a full investigation to find. This writes the
    real traceback to a local, gitignored file only; stdout is unchanged.
    """
    try:
        log_path = Path(root) / ".governance" / ".observation-failures.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = (
            f"{datetime.now(timezone.utc).isoformat()} "
            f"{type(error).__name__}: {error}\n"
            f"{traceback.format_exc()}\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
        # Keep the file bounded; this is a debugging aid, not an audit log.
        lines = log_path.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(lines) > 2000:
            log_path.write_text("".join(lines[-2000:]), encoding="utf-8")
    except OSError:
        pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def git(root, *args, optional=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(["git", "-C", str(root), *args], env=env,
                                capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ObservationError("Git observation unavailable") from error
    if result.returncode:
        if optional:
            return None
        raise ObservationError("Git observation failed: " + args[0])
    return result.stdout.decode("utf-8", "surrogateescape")


def read_json(path):
    if path.is_symlink():
        raise ObservationError("Symlinked governance input")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ObservationError("Missing or invalid governance input") from error


def _historical_inactive_logs(root, ticket_dir, key, status, dirty_paths, target_sha):
    """Recognize unchanged inactive legacy prose, never a writer or allocation.

    New/modified contracts, existing invalid intents and branch-owned material
    work retain the normal conservative checks. Only an identical README on
    the observed target and direct diagnostic log files qualify.
    """
    if status not in {"BACKLOG", "PLAN", "BLOCKED"} or ticket_dir.is_symlink():
        return False
    intent = ticket_dir / "intent.json"
    readme = ticket_dir / "README.md"
    if intent.exists() or intent.is_symlink() or readme.is_symlink() or not readme.is_file():
        return False
    prefix = "project/" + key + "/"
    changed = [name for name in dirty_paths if name.startswith(prefix)]
    if not changed or any(Path(name).parent.as_posix() != prefix.rstrip("/")
                          or not Path(name).name.endswith(".log.md")
                          or (root / name).is_symlink() or not (root / name).is_file()
                          for name in changed):
        return False
    committed = git(root, "show", target_sha + ":" + prefix + "README.md", optional=True)
    return committed is not None and readme.read_bytes() == committed.encode("utf-8", "surrogateescape")


def manifest_at(root):
    for rel in (".governance/manifest.json", ".governance/manifest.base.json",
                "governance/manifest.hub.json"):
        path = root / rel
        if path.exists():
            manifest = read_json(path)
            if manifest.get("schema") != "new-project.governance/v2":
                raise ObservationError("Unsupported governance manifest")
            return manifest
    raise ObservationError("Governance manifest missing")


def patterns(values):
    if (not isinstance(values, list) or not values or
            any(not isinstance(p, str) or not p or p.startswith(("/", "!")) or
                ".." in p.split("/") or "\\" in p or ":" in p or
                any(ord(c) < 32 for c in p) for p in values)):
        raise ObservationError("Expected nonempty repository-relative path patterns")
    return sorted(set(values))


def material(values):
    return [p for p in values if not path_ignored(p, TRACKING)]


def intersects(left, right):
    return any(globs_may_overlap(a, b) for a in left for b in right)


def unchanged_committed_legacy_carriers(root, head):
    """Observe old file carriers without assigning activity or ownership."""
    if (root / "project").is_symlink():
        raise ObservationError("Symlinked legacy project directory")
    entries = git(root, "ls-tree", "-r", "-z", head, "--", "project").split("\0")
    committed = {}
    directories = set()
    for entry in filter(None, entries):
        metadata, rel = entry.split("\t", 1)
        if not rel.startswith("project/ticket-"):
            continue
        mode, kind, oid = metadata.split()
        if (not re.fullmatch(r"project/ticket-[0-9]{3,}/.+", rel)
                or mode not in {"100644", "100755"} or kind != "blob"):
            raise ObservationError("Unsupported committed legacy carrier")
        committed[rel] = oid
        parent = Path(rel).parent
        while parent != Path("project"):
            directories.add(parent.as_posix())
            parent = parent.parent
    observed = set()
    observed_directories = set()
    for ticket in (root / "project").glob("ticket-*"):
        for path in (ticket, *ticket.rglob("*")):
            if path.is_symlink():
                raise ObservationError("Symlinked legacy carrier")
            rel = path.relative_to(root).as_posix()
            if path.is_dir():
                observed_directories.add(rel)
            elif path.is_file():
                observed.add(rel)
            else:
                raise ObservationError("Unsupported legacy carrier")
    if observed != set(committed) or observed_directories != directories:
        raise ObservationError("Legacy carriers differ from the committed bootstrap base")
    for rel, oid in committed.items():
        original = git(root, "cat-file", "blob", oid).encode("utf-8", "surrogateescape")
        if (root / rel).read_bytes() != original:
            raise ObservationError("Changed legacy carrier requires owner reconciliation")


def bootstrap_owned_paths(root, manifest, expected_digest):
    """A first allocator may acknowledge only exact installer-owned bytes.

    This is the same explicit owner confirmation as continuation's dirty
    digest. It suppresses no branch, ticket, WIP, lease or publication check.
    """
    _, current_digest, dirty = dirty_observation(root)
    if current_digest != expected_digest:
        raise ObservationError("Bootstrap dirty observation changed")
    receipt_path = root / ".subactor/receipts/bootstrap-adoption.json"
    if any(path.is_symlink() for path in (receipt_path, *receipt_path.parents)):
        raise ObservationError("Symlinked bootstrap receipt")
    receipt = read_json(receipt_path)
    head = git(root, "rev-parse", "HEAD").strip()
    common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    if (receipt.get("schema") != "new-project.bootstrap-adoption/v1"
            or receipt.get("baseSha") != head or receipt.get("commonGitDir") != common
            or receipt.get("grantsWriterAuthority") is not False
            or receipt.get("grantsPublicationAuthority") is not False):
        raise ObservationError("Bootstrap receipt bindings are invalid")
    kind = receipt.get("bootstrapKind", "legacy-scaffold")
    if kind == "fresh":
        for name in ("manifest.json", "manifest.lock.json", "manifest.base.json", "package-manifest.json"):
            if git(root, "cat-file", "-e", f"{head}:.governance/{name}", optional=True) is not None:
                raise ObservationError("Fresh bootstrap cannot replace committed governance")
    elif kind == "legacy-scaffold":
        original = json.loads(git(root, "show", f"{head}:.governance/manifest.json"))
        standard = original.get("standard", {})
        if (set(original) != {"schema", "standard"}
                or original.get("schema") != "wellmanifest.manifest/v1"
                or set(standard) != {"id", "version"}
                or standard.get("id") != "profile:baseline"
                or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(standard.get("version", "")))):
            raise ObservationError("Bootstrap requires a committed exact legacy scaffold")
    else:
        raise ObservationError("Unknown bootstrap kind")
    if (len(worktrees(root)) != 1
            or git(root, "for-each-ref", "--format=%(refname)", "refs/heads/ticket/")
            or (Path(common) / "new-project-ticket-high-water").exists()):
        raise ObservationError("Bootstrap acknowledgement is first-allocation only")
    if kind == "fresh":
        unchanged_committed_legacy_carriers(root, head)
    elif list((root / "project").glob("ticket-*")):
        raise ObservationError("Scaffold bootstrap acknowledgement is first-allocation only")
    lock = read_json(root / ".governance/manifest.lock.json")
    if (lock.get("standard", {}).get("publicationStatus") != "published"
            or lock.get("standard", {}).get("sourceRevision") != receipt.get("sourceRevision")):
        raise ObservationError("Bootstrap requires a published adoption lock")
    package = read_json(root / ".governance/package-manifest.json")
    admissible = {item["target"] for item in package["files"]}
    admissible.update({".gitignore", ".governance/manifest.lock.json"})
    for rel in manifest.get("requiredFiles", []):
        if git(root, "cat-file", "-e", f"{head}:{rel}", optional=True) is None:
            admissible.add(rel)
    files = receipt.get("files")
    if not isinstance(files, dict) or not files or set(files) - admissible:
        raise ObservationError("Bootstrap receipt includes paths outside adoption")
    if not set(lock["managedFiles"]).issubset(files):
        raise ObservationError("Bootstrap receipt omits managed files")
    for rel, checksum in files.items():
        patterns([rel])
        path = root / rel
        if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
                or not re.fullmatch(r"[0-9a-f]{64}", str(checksum))
                or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
                or (rel in lock["managedFiles"] and lock["managedFiles"][rel] != checksum)):
            raise ObservationError("Bootstrap payload changed or is not installed")
    return set(dirty).intersection(files)


def changes(root, base, head):
    ancestor = git(root, "merge-base", base, head, optional=True)
    if not ancestor:
        raise ObservationError("Unknown or unrelated branch ancestry")
    output = git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                 "--name-only", "-z", ancestor.strip(), head)
    return material([p for p in output.split("\0") if p])


def worktrees(root):
    output = git(root, "worktree", "list", "--porcelain", "-z")
    result, item = [], {}
    for field in output.split("\0"):
        if not field:
            if item:
                result.append(item)
                item = {}
        else:
            key, _, value = field.partition(" ")
            item[key] = value
    if item:
        result.append(item)
    if not result or "worktree" not in result[0] or "bare" in result[0]:
        raise ObservationError("Registered primary checkout unavailable")
    return result


def commit_trees(root, revision, *, ancestry_path=False):
    """Complete immutable snapshots, never path similarity or patch IDs."""
    options = ("--ancestry-path",) if ancestry_path else ()
    output = git(root, "log", "--format=%T", "--no-show-signature", *options, revision)
    trees = set(output.splitlines())
    if not trees or any(not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tree)
                        for tree in trees):
        raise ObservationError("Commit tree history unavailable")
    return trees


def dirty_observation(root):
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = iter(status.split("\0"))
    paths = set()
    for field in fields:
        if not field:
            continue
        paths.add(field[3:])
        if "R" in field[:2] or "C" in field[:2]:
            paths.add(next(fields))
    # Bind bytes, not just status letters: editing an already dirty file must
    # invalidate the observation. Never expose file content in the report.
    hashes = {}
    for rel in sorted(paths):
        path = root / rel
        if path.is_symlink():
            hashes[rel] = digest({"symlink": os.readlink(path)})
        elif path.is_file():
            with path.open("rb") as stream:
                checksum = hashlib.sha256()
                for chunk in iter(lambda: stream.read(65536), b""):
                    checksum.update(chunk)
                hashes[rel] = checksum.hexdigest()
        else:
            hashes[rel] = "absent-or-submodule"
    return material(sorted(paths)), digest({"status": status, "files": hashes}), sorted(paths)


def dirty_modified(root, paths):
    """Newest modification time of dirty paths: a recency observation, never writer identity."""
    newest = None
    for rel in paths:
        try:
            stamp = (root / rel).lstat().st_mtime
        except OSError:
            continue
        newest = stamp if newest is None or stamp > newest else newest
    return None if newest is None else datetime.fromtimestamp(newest, timezone.utc).isoformat(timespec="seconds")


def landed(path, ticket, target):
    """Whether the ticket directory is on the observed target and no ticket branch is outside it."""
    try:
        return delivery_landed(path, path / "project" / ticket, target)
    except subprocess.SubprocessError as error:
        raise ObservationError("Target ancestry observation failed") from error


def remote_heads(root):
    """Read advertisements, never fetch or print URLs/credential diagnostics."""
    result = {}
    for line in git(root, "ls-remote", "--heads", "origin").splitlines():
        fields = line.split("\t")
        if (len(fields) != 2 or
                not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[0]) or
                not fields[1].startswith("refs/heads/") or fields[1] in result or
                git(root, "check-ref-format", fields[1], optional=True) is None):
            raise ObservationError("Invalid remote advertisement")
        result[fields[1]] = fields[0]
    return result


def publication_observation(root, entries, target):
    """Evidence for a UI/CLI, not push permission or protected merge proof."""
    observation = {
        "schema": "new-project.publication-observation/v1",
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "readOnly": True, "grantsAuthority": False, "remote": "origin",
        "scope": "origin-heads",
        "status": "unavailable", "remoteRefsDigest": None,
        "targetRef": "refs/heads/" + target,
        "notObservedStages": ["pull-request", "checks", "approval",
                              "protected-merge", "release", "deployment"],
        "worktrees": [],
    }

    def unknown():
        observation["remoteRefsDigest"] = None
        observation["worktrees"] = [
            {"path": e["path"], "branch": e["branch"], "headSha": e["headSha"],
             "uncommittedPathCount": len(e["allDirtyPaths"]),
             "remoteContainingRefs": [], "unpublishedCommitCount": None,
             "sameBranchContainsHead": None, "headReachableFromTarget": None,
             "nextAction": "observe-remote"} for e in entries]
        return observation

    try:
        before = remote_heads(root)
        shallow = git(root, "rev-parse", "--is-shallow-repository").strip()
        if shallow not in {"true", "false"}:
            raise ObservationError("Shallow history observation unavailable")
        shallow = shallow == "true"
        known = {sha for sha in before.values()
                 if git(root, "cat-file", "-e", sha + "^{commit}", optional=True) is not None}
        unknown_objects = set(before.values()) - known
        observation["status"] = "partial" if unknown_objects or shallow else "observed"
        observation["remoteRefsDigest"] = digest(before)
        containment = {}

        def contains(head, remote_sha):
            if remote_sha == head:
                return True
            if remote_sha not in known:
                return None
            # rev-list errors are unavailable evidence, not a negative proof.
            key = (head, remote_sha)
            if key not in containment:
                count = int(git(root, "rev-list", "--count", head, "--not", remote_sha).strip())
                containment[key] = True if count == 0 else None if shallow else False
            return containment[key]

        for entry in entries:
            head = entry["headSha"]
            refs = sorted(ref for ref, sha in before.items() if contains(head, sha) is True)
            count = 0 if refs else None
            if count is None and not unknown_objects and not shallow:
                count = int(git(root, "rev-list", "--count", head, "--not", *sorted(known)).strip())
            branch_sha = before.get(entry["branch"])
            branch_contains = contains(head, branch_sha) if branch_sha else False
            target_sha = before.get(observation["targetRef"])
            target_contains = contains(head, target_sha) if target_sha else None
            dirty_count = len(entry["allDirtyPaths"])
            if dirty_count:
                action = "preserve-local-work"
            elif count is None:
                action = "observe-remote"
            elif count:
                action = "review-push-preconditions"
            elif branch_contains is not True:
                action = "reconcile-branch-binding"
            elif target_contains is not True:
                action = "observe-integration-evidence"
            else:
                action = "observe-review-release-deployment"
            observation["worktrees"].append({
                "path": entry["path"], "branch": entry["branch"], "headSha": head,
                "uncommittedPathCount": dirty_count, "remoteContainingRefs": refs,
                "unpublishedCommitCount": count, "sameBranchContainsHead": branch_contains,
                "headReachableFromTarget": target_contains, "nextAction": action,
            })
        if before != remote_heads(root):
            observation["status"] = "changed"
            return unknown()
        return observation
    except (ObservationError, ValueError):
        observation["status"] = "unavailable"
        return unknown()


def inspect(root, workstream, requested_paths=(), ticket=None, storage=None,
            observe_publication=False, expected_dirty_digest=None, recovery_intent=None,
            bootstrap_adoption_digest=None):
    root = Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    manifest = manifest_at(root)
    coordination = manifest["coordination"]
    stream = coordination["workstreams"][workstream]
    limit = coordination["maxActiveTicketsPerWorkstream"]
    if type(limit) is not int or limit < 1:
        raise ObservationError("Invalid workstream WIP limit")
    targets = manifest["delivery"]["targetBranches"]
    if not isinstance(targets, list) or len(targets) != 1:
        raise ObservationError("A unique declared target branch is required")
    target = targets[0]
    if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", target):
        raise ObservationError("Unsafe target branch")
    refs = git(root, "for-each-ref", "--format=%(refname) %(objectname)",
               "refs/heads", "refs/remotes")
    refs_map = dict(line.split(" ", 1) for line in refs.splitlines())
    target_refs = {ref: refs_map[ref] for ref in
                   ("refs/heads/" + target, "refs/remotes/origin/" + target)
                   if ref in refs_map}
    if not target_refs:
        raise ObservationError("Target branch observation missing; do not guess main")
    # Both observations are retained. Prefer the fetched remote, never fetch.
    target_sha = target_refs.get("refs/remotes/origin/" + target,
                                 target_refs.get("refs/heads/" + target))
    registrations = worktrees(root)
    primary = Path(registrations[0]["worktree"]).resolve()
    statuses = set(manifest["ticket"]["activeStatuses"])
    mode = storage or configured_mode(root)
    if mode not in {"files", "sqlite"}:
        raise ObservationError("Unsupported ticket storage")
    if bootstrap_adoption_digest and mode != "files":
        raise ObservationError("Bootstrap acknowledgement requires file allocation")
    bootstrap_owned = (bootstrap_owned_paths(primary, manifest, bootstrap_adoption_digest)
                       if bootstrap_adoption_digest else set())
    database = primary_database(root) if mode == "sqlite" else None
    records = {item["ticket"]: item for item in load_input(root, database=database)} if database and database.exists() else {}
    entries = []
    for registration in registrations:
        path = Path(registration["worktree"])
        if not path.is_dir() or path.is_symlink():
            raise ObservationError("Registered checkout unavailable; preserve and reconcile")
        head = git(path, "rev-parse", "--verify", "HEAD").strip()
        branch = (git(path, "symbolic-ref", "--quiet", "HEAD", optional=True) or "").strip()
        if head != registration.get("HEAD") or branch != registration.get("branch", ""):
            raise ObservationError("Checkout changed during observation")
        dirty, dirty_hash, all_dirty = dirty_observation(path)
        if bootstrap_adoption_digest and path == primary and dirty_hash != bootstrap_adoption_digest:
            raise ObservationError("Bootstrap changed during admission")
        ahead, behind = map(int, git(root, "rev-list", "--left-right", "--count",
                                    head + "..." + target_sha).split())
        match = TICKET.fullmatch(branch.removeprefix("refs/heads/"))
        ticket_id = "ticket-" + match[1] if match else None
        intent, active, status, activity_authority = None, False, None, "unresolved"
        recovering = (recovery_intent is not None and ticket_id == ticket
                      and path.resolve() == root and mode == "files")
        pending = bool(all_dirty or ahead or ticket_id in records or recovering)
        if ticket_id and pending:
            ticket_dir = path / "project" / ticket_id
            if ticket_dir.is_symlink():
                raise ObservationError("Symlinked ticket directory")
            record = records.get(ticket_id)
            if mode == "sqlite":
                if not record:
                    raise ObservationError("Branch ticket absent from selected SQLite input")
                intent = json.loads(record["files"]["intent.json"][0])
                readme = record["files"]["README.md"][0].decode("utf-8")
                status_match = re.search(r"(?mi)^-[ \t]+\*\*Status\*\*:[ \t]*([A-Z_]+)[ \t]*$", readme)
                if status_match is None:
                    raise ObservationError("SQLite ticket status unknown")
                status_override = status_match[1]
            elif recovering:
                if ticket_dir.exists():
                    raise ObservationError("Recovery cannot replace an existing ticket")
                intent = recovery_intent
                status_override = "IN_PROGRESS"
            else:
                intent = read_json(ticket_dir / "intent.json")
                status_override = None
            if intent.get("ticket") != ticket_id or intent.get("schema") not in (
                    "new-project.intent/v2", "new-project.intent/v3"):
                raise ObservationError("Branch/intent identity mismatch")
            patterns(intent.get("allowedPaths"))
            resolution = resolve_activity(path, ticket_dir, statuses, status_override=status_override)
            active, status = resolution.active, resolution.projectionStatus
            activity_authority = resolution.authority
            if status is None:
                raise ObservationError("Ticket status unknown")
        canonical = bool(ticket_id and path.resolve().parent == primary / ".worktrees"
                         and path.name.startswith(ticket_id + "--"))
        entries.append({"path": str(path.resolve()), "branch": branch or None,
                        "headSha": head, "ahead": ahead, "behind": behind,
                        "dirtyPaths": dirty, "allDirtyPaths": all_dirty, "dirtyDigest": dirty_hash,
                        "dirtyNewestModifiedAt": dirty_modified(path, all_dirty),
                        "pending": pending, "ticket": ticket_id,
                        "workstream": intent.get("workstream") if intent else None,
                        "allowedPaths": material(intent["allowedPaths"]) if intent else [],
                        "intentDigest": digest(intent) if intent else None,
                        "active": active, "status": status,
                        "activityAuthority": activity_authority, "canonical": canonical,
                        "writerAuthority": "unverified"})
    matches = [e for e in entries if ticket and e["ticket"] == ticket]
    if ticket and len(matches) != 1:
        raise ObservationError("Requested ticket has no unique registered checkout")
    selected = matches[0] if matches else None
    requested = material(patterns(list(requested_paths) if requested_paths else
                                  selected["allowedPaths"] if selected else stream["ownedPaths"]))
    if not requested:
        raise ObservationError("Material work scope required; use read-only inspection for carriers")
    if selected and (selected["workstream"] != workstream or not selected["canonical"]):
        raise ObservationError("Existing ticket requires ownership/layout reconciliation")
    if selected and any(not path_ignored(p, tuple(selected["allowedPaths"])) for p in requested):
        raise ObservationError("Requested scope exceeds the existing intent")
    comparison_sha = selected["headSha"] if selected else target_sha
    blockers = []
    active_tickets = set()
    assigned = {entry["ticket"] for entry in entries if entry["ticket"]}
    # Newly materialized ticket intent without its own branch is also pending
    # work. Do not resurrect inherited historical carrier copies in every tree.
    unassigned = {}
    for entry in entries:
        path = Path(entry["path"])
        if mode == "sqlite":
            candidates = {key: row for key, row in records.items() if key not in assigned}
        else:
            ids = {p.split("/")[1] for p in entry["allDirtyPaths"]
                   if re.match(r"^project/ticket-[0-9]{3,}/", p)}
            candidates = {key: None for key in ids if key not in assigned}
        for key, record in candidates.items():
            if key in unassigned:
                continue
            if mode == "sqlite":
                raw = record["files"]["README.md"][0].decode("utf-8")
                match = re.search(r"(?mi)^-[ \t]+\*\*Status\*\*:[ \t]*([A-Z_]+)[ \t]*$", raw)
                if match is None:
                    raise ObservationError("Unassigned ticket status unavailable")
                intent = json.loads(record["files"]["intent.json"][0])
                resolution = resolve_activity(path, path / "project" / key, statuses, status_override=match[1])
            else:
                ticket_dir = path / "project" / key
                resolution = resolve_activity(path, ticket_dir, statuses)
                if resolution.projectionStatus is None:
                    raise ObservationError("Unassigned ticket status unavailable")
                if not resolution.active and _historical_inactive_logs(
                        path, ticket_dir, key, resolution.projectionStatus,
                        entry["allDirtyPaths"], target_sha):
                    continue
                intent = read_json(ticket_dir / "intent.json")
            scope = material(patterns(intent.get("allowedPaths")))
            unassigned[key] = True
            if resolution.active and intent.get("workstream") == workstream:
                active_tickets.add(key)
            relevant = intersects(requested, scope) or intent.get("workstream") == workstream
            if resolution.active and mode == "files" and relevant and landed(path, key, target_sha):
                # A dirty carrier copy of a ticket already on the observed target
                # still projects activity (the conservative default is kept).
                # Name it instead of silently holding the workstream limit.
                blockers.append({"path": str(path), "branch": entry["branch"], "ticket": key,
                                 "active": resolution.active, "reason": "integrated-ticket-carrier"})
            elif resolution.active and (intersects(requested, scope) or (not scope and intent.get("workstream") == workstream)):
                blockers.append({"path": str(path), "branch": entry["branch"], "ticket": key,
                                 "active": resolution.active, "reason": "unassigned-ticket"})
    for entry in entries:
        if entry["active"] and entry["workstream"] == workstream:
            active_tickets.add(entry["ticket"])
        if entry is selected or not entry["pending"]:
            continue
        contribution = changes(root, comparison_sha, entry["headSha"])
        pending_paths = [p for p in entry["dirtyPaths"]
                         if not (Path(entry["path"]) == primary and p in bootstrap_owned)]
        contested = intersects(requested, pending_paths + contribution)
        reserved = entry["active"] and intersects(requested, entry["allowedPaths"])
        if contested or reserved:
            blockers.append({"path": entry["path"], "branch": entry["branch"],
                             "ticket": entry["ticket"], "active": entry["active"],
                             "reason": "scope-reservation" if reserved else "pending-delta"})
    checked = {e["branch"] for e in entries}
    branches = []
    target_trees = {}
    for ref, sha in sorted(refs_map.items()):
        if not ref.startswith("refs/heads/") or ref in checked or ref == "refs/heads/" + target:
            continue
        ahead, behind = map(int, git(root, "rev-list", "--left-right", "--count",
                                    sha + "..." + target_sha).split())
        branches.append({"branch": ref, "headSha": sha, "ahead": ahead, "behind": behind})
        if ahead and intersects(requested, changes(root, comparison_sha, sha)):
            # Only branches WITHOUT a registered checkout reach this path.
            # Require every unique snapshot AFTER divergence (not just HEAD).
            # An intentional new rollback must not match a pre-branch snapshot.
            # Preserve refs; this is neither terminal nor cleanup authority.
            ancestor = git(root, "merge-base", target_sha, sha).strip()
            if ancestor != target_sha and ancestor not in target_trees:
                target_trees[ancestor] = commit_trees(root, ancestor + ".." + target_sha, ancestry_path=True)
            if (ancestor != target_sha and
                    commit_trees(root, target_sha + ".." + sha) <= target_trees[ancestor]):
                continue
            blockers.append({"path": None, "branch": ref, "ticket": None,
                             "active": False, "reason": "unassigned-branch-delta"})
    required = ["current intent and session authority", "verified owner or accepted handoff",
                "controller lease CAS and fencing", "fresh preflight and governance gate"]
    if selected:
        # The selected checkout is excluded from peer contention, yet another
        # writer may have left uncommitted changes in it. Recency is evidence
        # only; the opt-in digest CAS detects any change since the caller's
        # previous observation.
        overlap = [p for p in selected["dirtyPaths"] if path_ignored(p, tuple(requested))]
        if expected_dirty_digest is not None and expected_dirty_digest != selected["dirtyDigest"]:
            blockers.append({"path": selected["path"], "branch": selected["branch"],
                             "ticket": selected["ticket"], "active": selected["active"],
                             "reason": "selected-checkout-changed"})
        elif expected_dirty_digest is None and overlap:
            required.append(f"confirm that {len(overlap)} uncommitted requested path(s) in the selected checkout "
                            f"(newest {selected['dirtyNewestModifiedAt']}) belong to this session, then pass "
                            f"--expect-dirty-digest {selected['dirtyDigest']}")
    route = "NEW_TICKET_CANDIDATE"
    if blockers:
        route = ("RECONCILE" if any(b["ticket"] is None or b["reason"] in {"unassigned-ticket", "integrated-ticket-carrier"}
                                    for b in blockers) else
                 "ASSIST_READ_ONLY" if any(b["active"] for b in blockers) else "HANDOFF_REQUIRED")
    elif selected:
        route = "REUSE_EXISTING"
    elif len(active_tickets) >= limit:
        route = "SERIALIZE"
    payload = {"schema": SCHEMA, "readOnly": True, "grantsAuthority": False,
               "createsWorktree": False, "scope": "registered-clone-local",
               "primaryCheckout": str(primary), "targetBranch": target,
               "targetObservations": target_refs, "remoteFreshness": "not-refreshed",
               "workstream": workstream, "requestedPaths": requested,
               "requestedTicket": ticket, "route": route, "diagnostic": None,
               "worktrees": entries, "uncheckedBranches": branches, "blockers": blockers,
               "activeTicketCount": len(active_tickets), "workstreamLimit": limit,
               "requiredBeforeWrite": required,
               "observationDigest": ""}
    if bootstrap_adoption_digest:
        payload["bootstrapOwnerAcknowledgement"] = {"dirtyDigest": bootstrap_adoption_digest,
                                                    "paths": sorted(bootstrap_owned),
                                                    "grantsWriterAuthority": False}
    storage_digest = digest({key: {"revision": row["revision"],
                                  "files": {name: hashlib.sha256(value[0]).hexdigest()
                                            for name, value in row["files"].items()}}
                             for key, row in records.items()})
    if observe_publication:
        payload["publication"] = publication_observation(root, entries, target)
    payload["observationDigest"] = digest({"refs": refs, "manifest": manifest, "report": payload,
                                          "ticketStorage": mode, "ticketInputDigest": storage_digest})
    if refs != git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes"):
        raise ObservationError("Refs changed during observation; retry")
    if manifest != manifest_at(root) or registrations != worktrees(root):
        raise ObservationError("Manifest or worktree registrations changed; retry")
    for entry in entries:
        if dirty_observation(Path(entry["path"]))[1] != entry["dirtyDigest"]:
            raise ObservationError("Workspace changed during observation; retry")
    if database and database.exists():
        if records != {item["ticket"]: item for item in load_input(root, database=database)}:
            raise ObservationError("Ticket database changed during observation; retry")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workstream", required=True)
    parser.add_argument("--ticket")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--allocation-check", action="store_true")
    parser.add_argument("--bootstrap-adoption-digest", metavar="SHA256",
                        help="Explicitly acknowledge owned first-scaffold installer bytes at this exact dirty digest")
    parser.add_argument("--storage", choices=["files", "sqlite"])
    parser.add_argument("--observe-publication", action="store_true",
                        help="Read origin refs twice without fetching; distinguish remote code from integration/release authority.")
    parser.add_argument("--expect-dirty-digest", metavar="SHA256",
                        help="With --ticket: dirtyDigest of the selected checkout from this session's previous observation; "
                             "a mismatch blocks reuse (clone-local CAS, not a lease).")
    args = parser.parse_args(argv)
    if args.expect_dirty_digest is not None and (
            not args.ticket or not re.fullmatch(r"[0-9a-f]{64}", args.expect_dirty_digest)):
        parser.error("--expect-dirty-digest requires --ticket and a lowercase SHA-256 digest")
    if args.bootstrap_adoption_digest is not None and (
            not args.allocation_check or args.ticket or args.storage == "sqlite"
            or not re.fullmatch(r"[0-9a-f]{64}", args.bootstrap_adoption_digest)):
        parser.error("--bootstrap-adoption-digest requires first file allocation and SHA-256")
    try:
        payload = inspect(args.root, args.workstream, args.path, args.ticket, args.storage,
                          args.observe_publication, args.expect_dirty_digest,
                          bootstrap_adoption_digest=args.bootstrap_adoption_digest)
    except (ObservationError, ActivityError, KeyError, TypeError, ValueError, OSError, StopIteration) as error:
        # Stdout stays generic — no exception content: remote URLs or
        # secret-bearing input never leak there. The real cause is written
        # to a local-only log instead of being discarded (see
        # _record_observation_failure).
        _record_observation_failure(args.root, error)

        print(json.dumps({"schema": SCHEMA, "readOnly": True, "grantsAuthority": False,
                          "createsWorktree": False, "route": "RECONCILE", "diagnostic": CODE,
                          "reason": "Observation incomplete or inconsistent; preserve work and reconcile. "
                                    "Real cause logged locally in .governance/.observation-failures.log "
                                    "(gitignored) — read it before opening a new ticket."}))
        return 3
    if args.allocation_check and payload["route"] != "NEW_TICKET_CANDIDATE":
        payload["diagnostic"] = CODE
    print(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    return 3 if payload["diagnostic"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
