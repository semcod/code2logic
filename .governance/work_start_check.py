#!/usr/bin/env python3
"""Read-only, clone-local work admission. Recommendations never grant authority."""
from __future__ import annotations

import argparse
import codecs
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import stat
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


class UnknownWorkstream(ObservationError):
    """The requested workstream is not declared; a caller input error, not divergent local work."""

    def __init__(self, declared):
        super().__init__("Workstream is not declared in the governance manifest")
        self.declared = declared


_OBSERVATION_LOG = ".subactor/receipts/work-start/observation-failures.log"
_OBSERVATION_LOG_MAX_BYTES = 128 * 1024


def _record_observation_failure(root, error):
    """Best-effort private, bounded diagnostics; never dirty or follow links."""
    try:
        import fcntl

        root = Path(root).absolute()
        # Do not infer ignore policy, or mutate a tracked diagnostic.
        if git(root, "check-ignore", "--quiet", "--", _OBSERVATION_LOG,
               optional=True) is None:
            return False
        if git(root, "ls-files", "--error-unmatch", "--", _OBSERVATION_LOG,
               optional=True) is not None:
            return False
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        with ExitStack() as stack:
            directory = os.open(root.anchor, flags)
            stack.callback(os.close, directory)
            for part in root.parts[1:]:
                directory = os.open(part, flags, dir_fd=directory)
                stack.callback(os.close, directory)
            for part in Path(_OBSERVATION_LOG).parent.parts:
                try:
                    os.mkdir(part, 0o700, dir_fd=directory)
                except FileExistsError:
                    pass
                directory = os.open(part, flags, dir_fd=directory)
                stack.callback(os.close, directory)
            info = os.fstat(directory)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                return False
            fd = os.open(Path(_OBSERVATION_LOG).name,
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=directory)
            stack.callback(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077
                    or info.st_size > _OBSERVATION_LOG_MAX_BYTES):
                return False
            previous = os.read(fd, _OBSERVATION_LOG_MAX_BYTES).decode("utf-8", "replace")
            entry = (f"{datetime.now(timezone.utc).isoformat()} "
                     f"{type(error).__name__}: {str(error)[:8192]}\n"
                     f"{traceback.format_exc()[-65536:]}\n")
            bounded = "".join((previous + entry).splitlines(keepends=True)[-2000:])
            data = bounded.encode("utf-8", "replace")[-_OBSERVATION_LOG_MAX_BYTES:]
            data = data.decode("utf-8", "ignore").encode("utf-8")
            os.lseek(fd, 0, os.SEEK_SET)
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError("Incomplete diagnostic write")
                view = view[count:]
            os.ftruncate(fd, len(data))
        return True
    except (OSError, ObservationError, ImportError, AttributeError, UnicodeError, NotImplementedError):
        return False


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


def quarantined(path, primary):
    """Checkouts parked under the repository's .worktrees/.quarantine/ directory are preserved evidence, not claims."""
    resolved = Path(path).resolve()
    quarantine_root = (Path(primary) / ".worktrees" / ".quarantine").resolve()
    return resolved != quarantine_root and resolved.is_relative_to(quarantine_root)


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


def bootstrap_historical_refs(root, head):
    """Observe integrated history only; preserve refs and independent ownership."""
    refs = git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/ticket/")
    if not refs:
        return refs
    if git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise ObservationError("Bootstrap history is incomplete")
    names = set()
    for line in refs.splitlines():
        ref, sha = line.split(" ", 1)
        # Equality is ambiguous: a newly reserved writer may still be at base.
        # A checked merge-base also refuses missing/unreadable ancestry.
        if sha == head or git(root, "merge-base", head, sha).strip() != sha:
            raise ObservationError("Bootstrap ticket ref is not strictly integrated")
        names.add(ref)
    leases = root / ".subactor/leases"
    if leases.is_symlink() or (leases.exists() and not leases.is_dir()):
        raise ObservationError("Bootstrap lease observation unavailable")
    for path in leases.glob("*.json"):
        lease = read_json(path)
        if lease.get("branchRef") not in names:
            continue
        try:
            expiry = datetime.fromisoformat(lease["expiresAt"].replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("unbound expiry")
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ObservationError("Bootstrap lease expiry unavailable") from error
        if expiry > datetime.now(timezone.utc):
            raise ObservationError("Bootstrap historical ref retains a live lease")
    return refs


WELLMAN_SCAFFOLD_PROFILES = frozenset({
    "wellmanifest/new-project",
    "profile:baseline",
    "profile:domain-pack",
    "profile:runtime-service",
    "profile:agent-executor",
    "profile:deployment",
    "profile:embedded-fleet",
    "profile:full",
})
WELLMAN_SCAFFOLD_VERSION_RE = re.compile(
    r"\A(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)


def bootstrap_scaffold_at_head(root, head):
    """Verify committed legacy provenance, or prove governance was absent.

    The published installer also accepts an exact untracked scaffold. Its
    receipt still binds the original clone/HEAD and every installed byte;
    absence in Git is not a reason to invent a preliminary scaffold commit.
    A checked tree read distinguishes absence from an unreadable Git object.
    """
    paths = set(git(root, "ls-tree", "-r", "--name-only", "-z", head,
                    "--", ".governance").split("\0")) - {""}
    if ".governance/manifest.json" not in paths:
        if paths:
            raise ObservationError("Untracked scaffold cannot replace committed governance")
        return
    original = json.loads(git(root, "show", f"{head}:.governance/manifest.json"))
    standard = original.get("standard", {}) if isinstance(original, dict) else {}
    if (not isinstance(original, dict) or set(original) != {"schema", "standard"}
            or original.get("schema") != "wellmanifest.manifest/v1"
            or not isinstance(standard, dict) or set(standard) != {"id", "version"}
            or standard.get("id") not in WELLMAN_SCAFFOLD_PROFILES
            or not isinstance(standard.get("version"), str)
            or not WELLMAN_SCAFFOLD_VERSION_RE.fullmatch(standard["version"])):
        raise ObservationError("Bootstrap requires an exact legacy scaffold")


def bootstrap_preserved_worktrees(root, head):
    """Observe canonical integrated checkouts; never retire or take over them.

    The existing historical-ref lease check remains independently required.
    Callers compare repeated observations; cleanliness is not writer authority.
    """
    inventory = worktrees(root)
    if Path(inventory[0]["worktree"]) != root:
        raise ObservationError("Bootstrap requires the registered primary checkout")
    common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    observed = []
    for item in inventory[1:]:
        branch = item.get("branch", "")
        match = re.fullmatch(r"refs/heads/ticket/([0-9]{3,})-([a-z0-9]+(?:-[a-z0-9]+)*)", branch)
        path = Path(item["worktree"])
        if (not match or set(item) != {"worktree", "HEAD", "branch"}
                or path != root / ".worktrees" / f"ticket-{match[1]}--{match[2]}"
                or any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_dir()):
            raise ObservationError("Bootstrap worktree is not a preserved canonical checkout")
        sha = git(path, "rev-parse", "HEAD").strip()
        if (sha != item["HEAD"] or sha == head
                or git(root, "merge-base", head, sha).strip() != sha
                or git(root, "rev-parse", branch).strip() != sha
                or git(path, "symbolic-ref", "HEAD").strip() != branch
                or Path(git(path, "rev-parse", "--show-toplevel").strip()) != path
                or git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").strip() != common):
            raise ObservationError("Bootstrap worktree bindings are not strictly integrated")
        # Non-default index flags and ignored submodules must not hide changes.
        flags = git(path, "ls-files", "-v", "-z").split("\0")
        if (any(field and field[0] != "H" for field in flags)
                or git(path, "status", "--porcelain=v1", "--untracked-files=all",
                       "--ignore-submodules=none")):
            raise ObservationError("Bootstrap preserved worktree is not observably clean")
        _, checksum, dirty = dirty_observation(path)
        if dirty:
            raise ObservationError("Bootstrap preserved worktree changed during observation")
        observed.append({"registration": item, "dirtyDigest": checksum})
    return {"inventory": inventory, "preserved": observed}


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
        bootstrap_scaffold_at_head(root, head)
    else:
        raise ObservationError("Unknown bootstrap kind")
    high_water = Path(common) / "new-project-ticket-high-water"
    if high_water.exists() or high_water.is_symlink():
        raise ObservationError("Bootstrap acknowledgement is first-allocation only")
    historical_refs = bootstrap_historical_refs(root, head)
    preserved_worktrees = bootstrap_preserved_worktrees(root, head)
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
    def verify_bootstrap_files():
        for rel, checksum in files.items():
            patterns([rel])
            path = root / rel
            if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
                    or not re.fullmatch(r"[0-9a-f]{64}", str(checksum))
                    or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
                    or (rel in lock["managedFiles"] and lock["managedFiles"][rel] != checksum)):
                raise ObservationError("Bootstrap payload changed or is not installed")

    verify_bootstrap_files()
    if (git(root, "rev-parse", "HEAD").strip() != head
            or bootstrap_historical_refs(root, head) != historical_refs
            or bootstrap_preserved_worktrees(root, head) != preserved_worktrees
            or high_water.exists() or high_water.is_symlink()):
        raise ObservationError("Bootstrap allocation state changed during observation")
    _, final_digest, final_dirty = dirty_observation(root)
    if final_digest != expected_digest or final_dirty != dirty:
        raise ObservationError("Bootstrap changed during admission")
    verify_bootstrap_files()
    return set(final_dirty).intersection(files)


def bootstrap_seed_paths(root, manifest):
    """A scope query may observe only exact first-installer required seeds.

    The allocator still requires its explicit dirty acknowledgement afterwards;
    this query changes no intent, ownership, reservation or authority.
    """
    root = Path(root).resolve()
    if root != Path(worktrees(root)[0]["worktree"]).resolve():
        return set()
    _, checksum, _ = dirty_observation(root)
    owned = bootstrap_owned_paths(root, manifest, checksum)
    from governance_check import initial_adoption_seed_paths
    lock = read_json(root / ".governance/manifest.lock.json")
    try:
        return owned & initial_adoption_seed_paths(
            root, git(root, "rev-parse", "HEAD").strip(),
            lock["standard"]["sourceRevision"], manifest)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise ObservationError("Bootstrap required seed evidence unavailable") from error


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
    index = git(root, "ls-files", "--stage", "-z")
    return material(sorted(paths)), digest({"status": status, "files": hashes, "index": index}), sorted(paths)


def outstanding_detached_paths(root, paths, target):
    """Subtract exact integrated bytes, without modifying or releasing the checkout."""
    trees = {}
    for item in git(root, "ls-tree", "-r", "--full-tree", "-z", target).split("\0"):
        if item:
            metadata, name = item.split("\t", 1)
            mode, kind, oid = metadata.split()
            if kind == "blob" and mode in {"100644", "100755"}:
                trees[name] = (mode, oid)
    indexes = {}
    for item in git(root, "ls-files", "--stage", "-z").split("\0"):
        if item:
            metadata, name = item.split("\t", 1)
            mode, oid, stage = metadata.split()
            indexes.setdefault(name, []).append((mode, oid, stage))
    outstanding = []
    for name in paths:
        path = root / name
        accepted = trees.get(name)
        if (not accepted or indexes.get(name) != [(*accepted, "0")]
                or any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()):
            outstanding.append(name)
            continue
        mode = "100755" if path.stat().st_mode & 0o100 else "100644"
        # Raw hashing deliberately ignores clean/textconv filters and index
        # flags: assume-unchanged cannot conceal different filesystem bytes.
        oid = git(root, "hash-object", "--no-filters", "--", name).strip()
        if (mode, oid) != accepted:
            outstanding.append(name)
    return outstanding


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
    except (ObservationError, ValueError, subprocess.SubprocessError):
        observation["status"] = "unavailable"
        return unknown()


CONTROLLER_STORE_SCHEMA = "subactor.repository-change-lease-store/v1"
FREE_LEASE_PHASES = {"closed", "cancelled", "released"}
REPOSITORY_REF = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
MAX_CONTROLLER_STATE_BYTES = 128 * 1024 * 1024
_CONTROLLER_CHUNK_BYTES = 65536
_MAX_JSON_DEPTH = 64
_MAX_JSON_STRING_CHARS = 1024 * 1024
_MAX_CAPTURED_ITEMS = 4096
_MAX_OBJECT_KEYS = 250000
_JSON_WS_RE = re.compile(r"[ \t\r\n]+")
_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
RESOURCE_ACTIONS = {
    "AVAILABLE": "Acquire the editing lease from the controller, then re-run work-start with --ticket before any write.",
    "HELD_BY_TICKET": "Continue only under the existing lease after verifying its owner, fencing token and expiry.",
    "HELD_EXPIRED": "The expired holder still blocks the resource until the controller releases it or records a "
                    "protected takeover; expiry alone never authorizes takeover.",
    "HELD_BY_OTHER": "Wait for the holder's release or a protected handoff; do not prepare an expiring admission now.",
    "UNAVAILABLE": "Restore controller access; do not infer availability from disjoint paths or retry an admission.",
}


class _ControllerStateChanged(ObservationError):
    pass


def _open_controller_state(store):
    path = Path(os.path.abspath(store)) / "state.json"
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ObservationError("Symlinked controller state")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ObservationError("Controller state must be a regular file")
    return stream


def _controller_bytes(store, *, max_bytes=MAX_CONTROLLER_STATE_BYTES):
    with _open_controller_state(store) as stream:
        chunks = []
        total = 0
        while True:
            chunk = stream.read(_CONTROLLER_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ObservationError("Controller state too large")
            chunks.append(chunk)
    return b"".join(chunks)


_DEFAULT_CONTROLLER_BYTES = _controller_bytes


def _stream_controller_digest(store, *, max_bytes=MAX_CONTROLLER_STATE_BYTES):
    with _open_controller_state(store) as stream:
        hasher = hashlib.sha256()
        total = 0
        while True:
            chunk = stream.read(_CONTROLLER_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ObservationError("Controller state too large")
            hasher.update(chunk)
    return hasher.hexdigest()


class _StreamJsonScanner:
    """Bounded RFC 8259 streaming reader with strict UTF-8 and duplicate-key rejection."""

    def __init__(self, stream, *, max_bytes=MAX_CONTROLLER_STATE_BYTES):
        self.stream = stream
        self.max_bytes = max_bytes
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.hasher = hashlib.sha256()
        self.total_bytes = 0
        self.buf = ""
        self.pos = 0
        self.eof = False

    def _fill(self):
        if self.eof:
            return False
        while True:
            chunk = self.stream.read(_CONTROLLER_CHUNK_BYTES)
            if not chunk:
                tail = self.decoder.decode(b"", final=True)
                self.eof = True
                if self.pos >= _CONTROLLER_CHUNK_BYTES:
                    self.buf = self.buf[self.pos:] + tail
                    self.pos = 0
                else:
                    self.buf += tail
                return bool(tail)
            self.total_bytes += len(chunk)
            if self.total_bytes > self.max_bytes:
                raise ObservationError("Controller state too large")
            self.hasher.update(chunk)
            decoded = self.decoder.decode(chunk, final=False)
            if self.pos >= _CONTROLLER_CHUNK_BYTES:
                self.buf = self.buf[self.pos:] + decoded
                self.pos = 0
            else:
                self.buf += decoded
            if decoded:
                return True

    def skip_ws(self):
        while True:
            match = _JSON_WS_RE.match(self.buf, self.pos)
            if match is not None:
                self.pos = match.end()
            if self.pos < len(self.buf) or self.eof:
                return
            self._fill()

    def peek(self):
        self.skip_ws()
        return self.buf[self.pos] if self.pos < len(self.buf) else ""

    def read_string(self):
        while True:
            try:
                value, end = json.decoder.scanstring(self.buf, self.pos + 1, True)
                if len(value) > _MAX_JSON_STRING_CHARS:
                    raise ValueError("JSON string exceeds controller bound")
                self.pos = end
                return value
            except json.JSONDecodeError:
                if self.eof or (len(self.buf) - self.pos) > (_MAX_JSON_STRING_CHARS * 6):
                    raise ValueError("Invalid JSON string") from None
                self._fill()

    def read_number(self, *, capture=False):
        while not self.eof and (len(self.buf) - self.pos) < 128:
            self._fill()
        while True:
            match = _JSON_NUMBER_RE.match(self.buf, self.pos)
            if match is None:
                raise ValueError("Invalid JSON number")
            if match.end() == len(self.buf) and not self.eof:
                if (len(self.buf) - self.pos) > 1024:
                    raise ValueError("Oversized JSON number")
                self._fill()
                continue
            break
        token = match.group(0)
        self.pos = match.end()
        if any(ch in token for ch in ".eE"):
            number = float(token)
            if not math.isfinite(number):
                raise ValueError("Non-finite JSON number")
            return number if capture else None
        if capture:
            if len(token) > 64:
                raise ValueError("Integer exceeds controller bound")
            return int(token)
        return None

    def read_literal(self):
        while not self.eof and (len(self.buf) - self.pos) < 5:
            self._fill()
        for literal, value in (("true", True), ("false", False), ("null", None)):
            if self.buf.startswith(literal, self.pos):
                self.pos += len(literal)
                return value
        raise ValueError("Invalid JSON literal")

    def skip_value(self, initial_depth):
        ch = self.peek()
        if not ch:
            raise ValueError("Unexpected EOF")
        if ch == '"':
            self.read_string()
            return
        if ch in "-0123456789":
            self.read_number(capture=False)
            return
        if ch in "tfn":
            self.read_literal()
            return
        if ch not in "{[":
            raise ValueError("Invalid JSON token")
        if initial_depth + 1 > _MAX_JSON_DEPTH:
            raise ValueError("JSON nesting too deep")
        self.pos += 1
        stack = [["obj", set(), True] if ch == "{" else ["arr", None, True]]
        while stack:
            kind, seen, first = stack[-1]
            cur = self.peek()
            if not cur:
                raise ValueError("Unterminated JSON container")
            if kind == "obj":
                if cur == "}" and first:
                    self.pos += 1
                    stack.pop()
                    continue
                if not first:
                    if cur == "}":
                        self.pos += 1
                        stack.pop()
                        continue
                    if cur != ",":
                        raise ValueError("Expected ',' or '}' in object")
                    self.pos += 1
                    cur = self.peek()
                if cur != '"':
                    raise ValueError("Expected object key")
                key = self.read_string()
                if key in seen or len(seen) >= _MAX_OBJECT_KEYS:
                    raise ValueError("Duplicate or excessive JSON key")
                seen.add(key)
                if self.peek() != ":":
                    raise ValueError("Expected ':' after object key")
                self.pos += 1
                stack[-1][2] = False
                val_ch = self.peek()
            else:
                if cur == "]" and first:
                    self.pos += 1
                    stack.pop()
                    continue
                if not first:
                    if cur == "]":
                        self.pos += 1
                        stack.pop()
                        continue
                    if cur != ",":
                        raise ValueError("Expected ',' or ']' in array")
                    self.pos += 1
                    val_ch = self.peek()
                else:
                    val_ch = cur
                stack[-1][2] = False
            if not val_ch:
                raise ValueError("Unexpected EOF")
            if val_ch == '"':
                self.read_string()
            elif val_ch in "-0123456789":
                self.read_number(capture=False)
            elif val_ch in "tfn":
                self.read_literal()
            elif val_ch in "{[":
                if initial_depth + len(stack) + 1 > _MAX_JSON_DEPTH:
                    raise ValueError("JSON nesting too deep")
                self.pos += 1
                stack.append(["obj", set(), True] if val_ch == "{" else ["arr", None, True])
            else:
                raise ValueError("Invalid JSON value")

    def capture_value(self, initial_depth):
        ch = self.peek()
        if not ch:
            raise ValueError("Unexpected EOF")
        if ch == '"':
            return self.read_string()
        if ch in "-0123456789":
            return self.read_number(capture=True)
        if ch in "tfn":
            return self.read_literal()
        if ch not in "{[":
            raise ValueError("Invalid JSON token")
        if initial_depth + 1 > _MAX_JSON_DEPTH:
            raise ValueError("JSON nesting too deep")
        self.pos += 1
        root_container = {} if ch == "{" else []
        stack = [["obj", root_container, True] if ch == "{" else ["arr", root_container, True]]
        items = 0
        while stack:
            kind, container, first = stack[-1]
            cur = self.peek()
            if not cur:
                raise ValueError("Unterminated JSON container")
            if kind == "obj":
                if cur == "}" and first:
                    self.pos += 1
                    stack.pop()
                    continue
                if not first:
                    if cur == "}":
                        self.pos += 1
                        stack.pop()
                        continue
                    if cur != ",":
                        raise ValueError("Expected ',' or '}' in object")
                    self.pos += 1
                    cur = self.peek()
                if cur != '"':
                    raise ValueError("Expected object key")
                key = self.read_string()
                if key in container:
                    raise ValueError("Duplicate JSON key")
                if self.peek() != ":":
                    raise ValueError("Expected ':' after object key")
                self.pos += 1
                stack[-1][2] = False
                val_ch = self.peek()
            else:
                key = None
                if cur == "]" and first:
                    self.pos += 1
                    stack.pop()
                    continue
                if not first:
                    if cur == "]":
                        self.pos += 1
                        stack.pop()
                        continue
                    if cur != ",":
                        raise ValueError("Expected ',' or ']' in array")
                    self.pos += 1
                    val_ch = self.peek()
                else:
                    val_ch = cur
                stack[-1][2] = False
            items += 1
            if items > _MAX_CAPTURED_ITEMS:
                raise ValueError("Captured controller entry exceeds bound")
            if not val_ch:
                raise ValueError("Unexpected EOF")
            if val_ch == '"':
                child = self.read_string()
                if kind == "obj":
                    container[key] = child
                else:
                    container.append(child)
            elif val_ch in "-0123456789":
                child = self.read_number(capture=True)
                if kind == "obj":
                    container[key] = child
                else:
                    container.append(child)
            elif val_ch in "tfn":
                child = self.read_literal()
                if kind == "obj":
                    container[key] = child
                else:
                    container.append(child)
            elif val_ch in "{[":
                if initial_depth + len(stack) + 1 > _MAX_JSON_DEPTH:
                    raise ValueError("JSON nesting too deep")
                self.pos += 1
                child = {} if val_ch == "{" else []
                if kind == "obj":
                    container[key] = child
                else:
                    container.append(child)
                stack.append(["obj", child, True] if val_ch == "{" else ["arr", child, True])
            else:
                raise ValueError("Invalid JSON value")
        return root_container


def _parse_controller_stream(stream, *, wanted_resources=None, wanted_leases=None,
                             max_bytes=MAX_CONTROLLER_STATE_BYTES):
    scanner = _StreamJsonScanner(stream, max_bytes=max_bytes)
    if scanner.peek() != "{":
        raise ValueError("Controller store root must be an object")
    scanner.pos += 1
    root_keys = set()
    schema = None
    saw_active = False
    saw_leases = False
    active_map = {}
    captured_leases = {}
    lease_keys = set()
    targets = set(wanted_leases or ())
    first_root = True
    while True:
        cur = scanner.peek()
        if not cur:
            raise ValueError("Unterminated controller store object")
        if cur == "}" and first_root:
            scanner.pos += 1
            break
        if not first_root:
            if cur == "}":
                scanner.pos += 1
                break
            if cur != ",":
                raise ValueError("Expected ',' or '}' in controller store")
            scanner.pos += 1
            cur = scanner.peek()
        if cur != '"':
            raise ValueError("Expected top-level key in controller store")
        top_key = scanner.read_string()
        if top_key in root_keys:
            raise ValueError("Duplicate JSON key")
        root_keys.add(top_key)
        if scanner.peek() != ":":
            raise ValueError("Expected ':' after top-level key")
        scanner.pos += 1
        first_root = False
        if top_key == "schema":
            if scanner.peek() != '"':
                raise ValueError("schema must be a string")
            schema = scanner.read_string()
        elif top_key == "active":
            if scanner.peek() != "{":
                raise ValueError("active must be an object")
            scanner.pos += 1
            saw_active = True
            seen_active = set()
            first_active = True
            while True:
                ac = scanner.peek()
                if not ac:
                    raise ValueError("Unterminated active object")
                if ac == "}" and first_active:
                    scanner.pos += 1
                    break
                if not first_active:
                    if ac == "}":
                        scanner.pos += 1
                        break
                    if ac != ",":
                        raise ValueError("Expected ',' or '}' in active")
                    scanner.pos += 1
                    ac = scanner.peek()
                if ac != '"':
                    raise ValueError("Expected resource key in active")
                res_key = scanner.read_string()
                if res_key in seen_active or len(seen_active) >= _MAX_OBJECT_KEYS:
                    raise ValueError("Duplicate or excessive active key")
                seen_active.add(res_key)
                if scanner.peek() != ":":
                    raise ValueError("Expected ':' in active")
                scanner.pos += 1
                first_active = False
                vc = scanner.peek()
                if vc == '"':
                    holder_val = scanner.read_string()
                elif vc == "n":
                    holder_val = scanner.read_literal()
                    if holder_val is not None:
                        raise ValueError("Invalid active value")
                else:
                    raise ValueError("Active resource holder must be string or null")
                if wanted_resources is None or res_key in wanted_resources:
                    if len(active_map) >= _MAX_CAPTURED_ITEMS:
                        raise ValueError("Captured active map exceeds bound")
                    active_map[res_key] = holder_val
                    if isinstance(holder_val, str):
                        targets.add(holder_val)
        elif top_key == "leases":
            if scanner.peek() != "{":
                raise ValueError("leases must be an object")
            scanner.pos += 1
            saw_leases = True
            first_lease = True
            while True:
                lc = scanner.peek()
                if not lc:
                    raise ValueError("Unterminated leases object")
                if lc == "}" and first_lease:
                    scanner.pos += 1
                    break
                if not first_lease:
                    if lc == "}":
                        scanner.pos += 1
                        break
                    if lc != ",":
                        raise ValueError("Expected ',' or '}' in leases")
                    scanner.pos += 1
                    lc = scanner.peek()
                if lc != '"':
                    raise ValueError("Expected lease key")
                lid = scanner.read_string()
                if lid in lease_keys or len(lease_keys) >= _MAX_OBJECT_KEYS:
                    raise ValueError("Duplicate or excessive lease key")
                lease_keys.add(lid)
                if scanner.peek() != ":":
                    raise ValueError("Expected ':' after lease key")
                scanner.pos += 1
                first_lease = False
                if lid in targets:
                    lease_obj = scanner.capture_value(initial_depth=2)
                    if not isinstance(lease_obj, dict):
                        raise ValueError("Lease record must be an object")
                    captured_leases[lid] = lease_obj
                else:
                    scanner.skip_value(initial_depth=2)
        else:
            scanner.skip_value(initial_depth=1)
    if scanner.peek() != "":
        raise ValueError("Trailing data in controller state")
    if schema != CONTROLLER_STORE_SCHEMA:
        raise ValueError("unsupported store")
    if not saw_active:
        raise KeyError("active")
    if not saw_leases:
        raise KeyError("leases")
    return {
        "schema": schema,
        "active": active_map,
        "leases": captured_leases,
        "leaseKeys": lease_keys,
        "stateDigest": scanner.hasher.hexdigest(),
    }


def read_controller_projection(store, *, resources=(), lease_ids=(),
                               max_bytes=MAX_CONTROLLER_STATE_BYTES):
    """Stream-validate controller state.json and extract only requested active/lease entries."""
    wanted_resources = set(resources) if resources else None
    wanted_leases = {lid for lid in lease_ids if isinstance(lid, str)}
    with _open_controller_state(store) as stream:
        first = _parse_controller_stream(
            stream, wanted_resources=wanted_resources,
            wanted_leases=wanted_leases, max_bytes=max_bytes)
        missing_present = {
            holder_id for holder_id in first["active"].values()
            if isinstance(holder_id, str)
            and holder_id not in first["leases"]
            and holder_id in first["leaseKeys"]
        }
        if missing_present:
            stream.seek(0)
            second = _parse_controller_stream(
                stream, wanted_resources=wanted_resources,
                wanted_leases=wanted_leases | missing_present, max_bytes=max_bytes)
            if second["stateDigest"] != first["stateDigest"]:
                raise _ControllerStateChanged("Controller state changed during read")
            first = second
    first.pop("leaseKeys", None)
    return first


def controller_observation(store, repository, target, ticket=None):
    """Read-only availability of the controller's exclusive editing resource; never a grant or a queue entry."""
    observation = {
        "schema": "new-project.editing-resource-observation/v1",
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "readOnly": True, "grantsAuthority": False, "queueSupported": False,
        "repositoryRef": repository, "targetBranch": target, "ticket": ticket,
        "resource": digest({"repositoryRef": repository, "targetBranch": target}),
        "state": "UNAVAILABLE", "reason": None, "holder": None, "stateDigest": None,
    }
    custom_bytes = _controller_bytes is not _DEFAULT_CONTROLLER_BYTES
    try:
        if custom_bytes:
            raw = _controller_bytes(store)
        else:
            state = read_controller_projection(store, resources=(observation["resource"],))
    except FileNotFoundError:
        observation["reason"] = "controller-store-missing"
    except _ControllerStateChanged:
        observation["reason"] = "controller-state-changed"
    except (OSError, ObservationError):
        observation["reason"] = "controller-state-unreadable"
    except (ValueError, KeyError, TypeError, AttributeError):
        observation["reason"] = "controller-state-invalid"
    else:
        try:
            if custom_bytes:
                state = _parse_controller_stream(
                    io.BytesIO(raw), wanted_resources={observation["resource"]})
                missing_present = {
                    hid for hid in state["active"].values()
                    if isinstance(hid, str) and hid not in state["leases"] and hid in state["leaseKeys"]
                }
                if missing_present:
                    state = _parse_controller_stream(
                        io.BytesIO(raw), wanted_resources={observation["resource"]},
                        wanted_leases=missing_present)
            holder_id = state["active"].get(observation["resource"])
            holder = None if holder_id is None else state["leases"][holder_id]
            if holder is not None:
                expires = datetime.fromisoformat(holder["expiresAt"].replace("Z", "+00:00"))
                if expires.tzinfo is None or not isinstance(holder["phase"], str):
                    raise ValueError("invalid holder")
        except (ValueError, KeyError, TypeError, AttributeError):
            observation["reason"] = "controller-state-invalid"
        else:
            try:
                changed = (_controller_bytes(store) != raw if custom_bytes
                           else _stream_controller_digest(store) != state["stateDigest"])
            except (OSError, ObservationError):
                changed = True
            if changed:
                observation["reason"] = "controller-state-changed"
            elif holder is None or holder["phase"] in FREE_LEASE_PHASES:
                observation["state"] = "AVAILABLE"
                observation["stateDigest"] = state["stateDigest"]
            else:
                # A safe reference only: no owner session, credential or plan.
                observation["holder"] = {"leaseId": holder_id, "ticketId": holder.get("ticketId"),
                                         "phase": holder["phase"], "expiresAt": holder["expiresAt"]}
                if holder["phase"] == "expired" or expires <= datetime.now(timezone.utc):
                    observation["state"] = "HELD_EXPIRED"
                elif ticket is not None and holder.get("ticketId") == ticket:
                    observation["state"] = "HELD_BY_TICKET"
                else:
                    observation["state"] = "HELD_BY_OTHER"
                observation["stateDigest"] = state["stateDigest"]
    observation["nextAction"] = RESOURCE_ACTIONS[observation["state"]]
    return observation


def inspect(root, workstream, requested_paths=(), ticket=None, storage=None,
            observe_publication=False, expected_dirty_digest=None, recovery_intent=None,
            bootstrap_adoption_digest=None, controller=None):
    root = Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    manifest = manifest_at(root)
    coordination = manifest["coordination"]
    declared = coordination["workstreams"]
    if workstream not in declared:
        raise UnknownWorkstream(sorted(name for name in declared
                                       if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name)))
    stream = declared[workstream]
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
                try:
                    intent = read_json(ticket_dir / "intent.json")
                except ObservationError:
                    # A quarantined checkout may hold an interrupted merge. Record it
                    # instead of aborting every allocation; its Git delta is still
                    # compared below as pending work.
                    if not quarantined(path, primary):
                        raise
                    intent = None
                status_override = None
            if intent is None:
                active, status, activity_authority = False, "QUARANTINED_UNREADABLE", "quarantine"
            else:
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
        if (pending_paths and Path(entry["path"]) != primary and entry["branch"] is None
                and entry["ticket"] is None and not entry["active"] and entry["ahead"] == 0):
            pending_paths = outstanding_detached_paths(Path(entry["path"]), pending_paths, target_sha)
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
    if controller:
        payload["editingResource"] = controller_observation(*controller, target, ticket)
    if refs != git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes"):
        raise ObservationError("Refs changed during observation; retry")
    if manifest != manifest_at(root) or registrations != worktrees(root):
        raise ObservationError("Manifest or worktree registrations changed; retry")
    disjoint_peer_updated = False
    for entry in entries:
        new_dirty, new_dirty_hash, new_all_dirty = dirty_observation(Path(entry["path"]))
        if new_dirty_hash != entry["dirtyDigest"]:
            _reconcile_disjoint_peer_mutation(
                entry, new_dirty, new_dirty_hash, new_all_dirty,
                root=root, primary=primary, selected=selected, requested=requested,
                comparison_sha=comparison_sha, statuses=statuses, mode=mode, records=records)
            disjoint_peer_updated = True
    if database and database.exists():
        if records != {item["ticket"]: item for item in load_input(root, database=database)}:
            raise ObservationError("Ticket database changed during observation; retry")
    if disjoint_peer_updated and observe_publication:
        payload["publication"] = publication_observation(root, entries, target)
        if refs != git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes"):
            raise ObservationError("Refs changed during observation; retry")
    payload["observationDigest"] = ""
    payload["observationDigest"] = digest({"refs": refs, "manifest": manifest, "report": payload,
                                          "ticketStorage": mode, "ticketInputDigest": storage_digest})
    return payload


def _reconcile_disjoint_peer_mutation(entry, new_dirty, new_dirty_hash, new_all_dirty, *,
                                      root, primary, selected, requested, comparison_sha,
                                      statuses, mode, records):
    """Allow uncommitted progress only inside an unchanged, non-overlapping peer ticket checkout."""
    peer_path = Path(entry["path"]).resolve()
    ticket_id = entry["ticket"]
    if (entry is selected or peer_path == root or peer_path == primary
            or not ticket_id or not entry["branch"] or entry["intentDigest"] is None
            or entry["status"] == "QUARANTINED_UNREADABLE"
            or not peer_path.is_dir() or peer_path.is_symlink()
            or quarantined(peer_path, primary)):
        raise ObservationError("Workspace changed during observation; retry")
    head = git(peer_path, "rev-parse", "--verify", "HEAD").strip()
    branch = (git(peer_path, "symbolic-ref", "--quiet", "HEAD", optional=True) or "").strip()
    if head != entry["headSha"] or branch != entry["branch"]:
        raise ObservationError("Workspace changed during observation; retry")
    new_pending = bool(new_all_dirty or entry["ahead"] or ticket_id in records)
    if not new_pending or new_pending != entry["pending"]:
        raise ObservationError("Workspace changed during observation; retry")
    for dirty_path in (*entry["allDirtyPaths"], *new_all_dirty):
        carrier = re.match(r"^project/(ticket-[0-9]{3,})/", dirty_path)
        if carrier and carrier.group(1) != ticket_id:
            raise ObservationError("Workspace changed during observation; retry")
    ticket_dir = peer_path / "project" / ticket_id
    if ticket_dir.is_symlink():
        raise ObservationError("Workspace changed during observation; retry")
    if mode == "sqlite":
        record = records.get(ticket_id)
        if not record:
            raise ObservationError("Workspace changed during observation; retry")
        re_intent = json.loads(record["files"]["intent.json"][0])
        readme = record["files"]["README.md"][0].decode("utf-8")
        status_match = re.search(r"(?mi)^-[ \t]+\*\*Status\*\*:[ \t]*([A-Z_]+)[ \t]*$", readme)
        if status_match is None:
            raise ObservationError("Workspace changed during observation; retry")
        status_override = status_match[1]
    else:
        re_intent = read_json(ticket_dir / "intent.json")
        status_override = None
    if digest(re_intent) != entry["intentDigest"]:
        raise ObservationError("Workspace changed during observation; retry")
    re_res = resolve_activity(peer_path, ticket_dir, statuses, status_override=status_override)
    if ((re_res.active, re_res.projectionStatus, re_res.authority)
            != (entry["active"], entry["status"], entry["activityAuthority"])):
        raise ObservationError("Workspace changed during observation; retry")
    if (intersects(requested, entry["allowedPaths"])
            or intersects(requested, entry["dirtyPaths"])
            or intersects(requested, new_dirty)
            or intersects(requested, changes(root, comparison_sha, entry["headSha"]))):
        raise ObservationError("Workspace changed during observation; retry")
    entry["dirtyPaths"] = new_dirty
    entry["allDirtyPaths"] = new_all_dirty
    entry["dirtyDigest"] = new_dirty_hash
    entry["dirtyNewestModifiedAt"] = dirty_modified(peer_path, new_all_dirty)
    entry["pending"] = new_pending


def refresh_autonomy_board(root):
    """Best effort: every work start rewrites the ignored GOV-IDLE-TAKEOVER board; it never changes the route."""
    checker = Path(__file__).resolve().parent / "idle_takeover.py"
    if not checker.is_file():
        return
    try:
        spec = importlib.util.spec_from_file_location("work_start_idle_takeover", checker)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        board = module.observe(Path(root))
        path = module.write_board(board)
    except Exception:  # noqa: BLE001 - the board is advisory; observation errors must not alter the route
        return
    eligible = [item["ticket"] for item in board["tickets"] if item["state"] == "IDLE_TAKEOVER_ELIGIBLE"]
    print(f"autonomy board: {path}" + (f"; idle takeover candidates: {', '.join(eligible)}" if eligible else ""),
          file=sys.stderr)


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
    parser.add_argument("--controller-store", type=Path, metavar="DIR",
                        help="Read-only availability of the controller editing resource (state.json); never a grant.")
    parser.add_argument("--controller-repository", metavar="OWNER/NAME",
                        help="Exact repository reference the controller resource is bound to (with --controller-store).")
    parser.add_argument("--expect-dirty-digest", metavar="SHA256",
                        help="With --ticket: dirtyDigest of the selected checkout from this session's previous observation; "
                             "a mismatch blocks reuse (clone-local CAS, not a lease).")
    args = parser.parse_args(argv)
    if args.expect_dirty_digest is not None and (
            not args.ticket or not re.fullmatch(r"[0-9a-f]{64}", args.expect_dirty_digest)):
        parser.error("--expect-dirty-digest requires --ticket and a lowercase SHA-256 digest")
    if (args.controller_store is None) != (args.controller_repository is None) or (
            args.controller_repository is not None and not REPOSITORY_REF.fullmatch(args.controller_repository)):
        parser.error("--controller-store and --controller-repository OWNER/NAME must be passed together")
    if args.bootstrap_adoption_digest is not None and (
            not args.allocation_check or args.ticket or args.storage == "sqlite"
            or not re.fullmatch(r"[0-9a-f]{64}", args.bootstrap_adoption_digest)):
        parser.error("--bootstrap-adoption-digest requires first file allocation and SHA-256")
    try:
        payload = inspect(args.root, args.workstream, args.path, args.ticket, args.storage,
                          args.observe_publication, args.expect_dirty_digest,
                          bootstrap_adoption_digest=args.bootstrap_adoption_digest,
                          controller=(args.controller_store, args.controller_repository)
                          if args.controller_store else None)
    except (ObservationError, ActivityError, KeyError, TypeError, ValueError, OSError, StopIteration) as error:
        # Stdout stays generic — no exception content: remote URLs or
        # secret-bearing input never leak there. The real cause is written
        # to a local-only log instead of being discarded (see
        # _record_observation_failure).
        if isinstance(error, UnknownWorkstream):
            # The whole cause fits on stdout, so nothing is logged. Declared
            # names come from the checked-in manifest and disclose nothing;
            # the caller's raw argument is not echoed.
            print(json.dumps({"schema": SCHEMA, "readOnly": True, "grantsAuthority": False,
                              "createsWorktree": False, "route": "RECONCILE", "diagnostic": CODE,
                              "reason": "GOV-WORKSTREAM-001: --workstream is not declared in the governance "
                                        "manifest; no checkout needs reconciling. Declared workstreams: "
                                        + (", ".join(error.declared) or "none") + "."}))
            return 3
        logged = _record_observation_failure(args.root, error)

        print(json.dumps({"schema": SCHEMA, "readOnly": True, "grantsAuthority": False,
                          "createsWorktree": False, "route": "RECONCILE", "diagnostic": CODE,
                          "reason": "Observation incomplete or inconsistent; preserve work and reconcile. "
                                    + ("Real cause logged locally in " + _OBSERVATION_LOG
                                       + " (ignored by Git) — read it before opening a new ticket."
                                       if logged else "Local diagnostic was not written; preserve work "
                                       "and inspect the existing checkout and ignore policy.")}))
        return 3
    if args.allocation_check and payload["route"] != "NEW_TICKET_CANDIDATE":
        payload["diagnostic"] = CODE
    refresh_autonomy_board(args.root)
    print(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    return 3 if payload["diagnostic"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
