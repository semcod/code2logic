#!/usr/bin/env python3
"""Detect overlapping dirty/committed paths across sibling worktrees.

This is the *active-development* companion to workspace_lifecycle_check.py.
That checker is terminal (leftover worktrees after merge). This one fails
closed when two or more checkouts of the same repository identity edit the
same paths, or when their IN_PROGRESS allowedPaths overlap without
conflictsWith.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_previous_bytecode_policy = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    try:
        from ticket_activity import ActivityError, ActivityReadBatch
        from ticket_activity import resolve as resolve_ticket_activity
    except ModuleNotFoundError:
        _activity_spec = importlib.util.spec_from_file_location(
            "ticket_activity", Path(__file__).with_name("ticket_activity.py")
        )
        if _activity_spec is None or _activity_spec.loader is None:
            raise
        _activity_module = importlib.util.module_from_spec(_activity_spec)
        sys.modules[_activity_spec.name] = _activity_module
        _activity_spec.loader.exec_module(_activity_module)
        ActivityError = _activity_module.ActivityError
        ActivityReadBatch = _activity_module.ActivityReadBatch
        resolve_ticket_activity = _activity_module.resolve
finally:
    sys.dont_write_bytecode = _previous_bytecode_policy


REPORT_SCHEMA = "new-project.worktree-overlap-report/v1"
SCP_REMOTE_RE = re.compile(r"^(?:[^@/]+@)?([^:/]+):(.+)$")
TICKET_DIRECTORY_RE = re.compile(r"^ticket-([0-9]+)$")
DEFAULT_IGNORE = (
    "TODO.md",
    "project/TICKETS.md",
    "project/ticket-*/**",
    "node_modules/**",
    ".venv/**",
    "venv/**",
    "__pycache__/**",
    "**/__pycache__/**",
)
DEFAULT_WORKTREE_DIRNAMES = ("worktrees", ".worktrees", ".workspaces")


@dataclass(order=True)
class Finding:
    code: str
    severity: str
    message: str
    remediation: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class TicketScope:
    ticket: str
    workstream: str | None
    allowed_paths: tuple[str, ...]
    conflicts_with: tuple[str, ...]
    path: str


@dataclass(frozen=True)
class Checkout:
    path: Path
    common_git_dir: Path
    identity: str
    head: str | None
    branch: str | None
    dirty: bool
    pending: bool
    dirty_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    tickets: tuple[TicketScope, ...]
    activity_errors: tuple[str, ...]


class AuditError(RuntimeError):
    """The overlap audit could not complete safely."""


def load_worktrees_contract():
    """Load the exact managed Worktrees inventory without bytecode writes."""
    script = Path(__file__).resolve()
    candidates = (
        script.with_name("worktree_path_check.py"),
        script.parent.parent / "subprojects" / "worktrees" / "conformance.py",
    )
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        raise AuditError("the managed Worktrees conformance module is missing")
    spec = importlib.util.spec_from_file_location("overlap_worktrees_contract", source)
    if spec is None or spec.loader is None:
        raise AuditError(f"cannot load Worktrees conformance from {source}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except (ImportError, OSError, ValueError) as error:
        raise AuditError(f"cannot load Worktrees conformance: {error}") from error
    finally:
        sys.dont_write_bytecode = previous
        sys.modules.pop(spec.name, None)
    return module


# git exports these into hooks. Inherited, they override `git -C <path>` and
# point every subprocess back at the repository being committed, which silently
# collapses the whole workspace into a single checkout and passes the gate.
GIT_SCOPE_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_INDEX_VERSION",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)


def detached_git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in GIT_SCOPE_ENV}


def run_git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=False,
            timeout=20,
            env=detached_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AuditError(f"git failed for {root}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode('utf-8', 'surrogateescape').strip()
        raise AuditError(f"git {' '.join(arguments)} failed for {root}: {detail}")
    # Decode explicitly: text mode would translate CR/LF inside literal -z
    # filenames. A terminating NUL protects path suffixes from metadata trimming.
    return result.stdout.decode('utf-8', 'surrogateescape').rstrip("\r\n")


def local_remote_path(root: Path, remote: str) -> Path | None:
    if remote.startswith("file://"):
        parsed = urlparse(remote)
        return Path(parsed.path).resolve()
    candidate = Path(remote).expanduser()
    if candidate.is_absolute() or remote.startswith(("./", "../")):
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate.resolve()
    return None


def normalized_network_remote(remote: str) -> str:
    value = remote.strip().rstrip("/")
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise AuditError("Network remote has an invalid host or port") from error
    if parsed.scheme and parsed.hostname:
        path = parsed.path.lstrip("/")
        host = parsed.hostname.lower()
        default_port = {"ssh": 22, "https": 443, "http": 80, "git": 9418}.get(parsed.scheme)
        if port is not None and port != default_port:
            host = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    else:
        match = SCP_REMOTE_RE.fullmatch(value)
        if not match:
            return f"remote:{value.removesuffix('.git').lower()}"
        host, path = match.groups()
        host = host.lower()
    return f"remote:{host}/{path.removesuffix('.git').lower()}"


def repository_identity(root: Path, seen: set[Path] | None = None) -> str:
    resolved = root.resolve()
    visited = set() if seen is None else set(seen)
    if resolved in visited:
        raise AuditError(f"local origin cycle detected at {resolved}")
    visited.add(resolved)
    try:
        remote = run_git(resolved, "remote", "get-url", "origin")
    except AuditError as error:
        if "No such remote" not in str(error):
            raise
        # Linked checkouts before remote creation still share a repository.
        # Their different working directories must not hide competing writes.
        common = Path(run_git(resolved, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        return f"local-repository:{common}"
    local = local_remote_path(resolved, remote)
    if local is not None and (local / ".git").exists():
        return repository_identity(local, visited)
    if local is not None:
        return f"local:{local}"
    return normalized_network_remote(remote)


def registered_worktrees(path: Path) -> list[Path]:
    worktrees: list[Path] = []
    for line in run_git(path, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            worktrees.append(Path(line.removeprefix("worktree ")).resolve())
    return worktrees


def primary_checkout(checkouts: list[Checkout]) -> Checkout:
    owners = [
        checkout
        for checkout in checkouts
        if checkout.common_git_dir == checkout.path / ".git"
    ]
    return min(
        owners or checkouts,
        key=lambda item: (len(item.path.parts), str(item.path)),
    )


def workspace_inventory(checkouts: list[Checkout]) -> dict[str, Any]:
    """Compose owner layout classes with adopter-owned duplicate-clone evidence."""
    contract = load_worktrees_contract()
    path_style = "windows" if os.name == "nt" else "posix"
    clone_groups: dict[Path, list[Checkout]] = {}
    identity_groups: dict[str, list[Checkout]] = {}
    for checkout in checkouts:
        clone_groups.setdefault(checkout.common_git_dir, []).append(checkout)
        identity_groups.setdefault(checkout.identity, []).append(checkout)

    layout_entries: dict[Path, dict[str, Any]] = {}
    for _, group in sorted(clone_groups.items(), key=lambda item: str(item[0])):
        primary = primary_checkout(group)
        try:
            observed = contract.inventory(
                repository=primary.identity,
                repository_name=primary.path.name,
                primary_checkout=str(primary.path),
                registered=[
                    {
                        "path": str(checkout.path),
                        "head": checkout.head,
                        "branch": checkout.branch,
                        "detached": checkout.branch is None,
                    }
                    for checkout in group
                ],
                path_style=path_style,
            )
        except (TypeError, ValueError) as error:
            raise AuditError(f"Worktrees inventory failed: {error}") from error
        if observed.get("readOnly") is not True:
            raise AuditError("Worktrees inventory did not declare readOnly=true")
        for entry in observed["entries"]:
            layout_entries[Path(entry["path"])] = entry

    authoritative_clone = {
        identity: primary_checkout(group).common_git_dir
        for identity, group in identity_groups.items()
    }
    entries: list[dict[str, Any]] = []
    for checkout in sorted(checkouts, key=lambda item: str(item.path)):
        layout = layout_entries.get(checkout.path)
        if layout is None:
            raise AuditError(f"Worktrees inventory omitted {checkout.path}")
        duplicate = checkout.common_git_dir != authoritative_clone[checkout.identity]
        anomalies = list(layout["anomalies"])
        if duplicate:
            anomalies.append("duplicate-clone")
        entries.append({
            "path": str(checkout.path),
            "identity": checkout.identity,
            "branch": checkout.branch,
            "head": checkout.head,
            "dirty": checkout.dirty,
            "classification": layout["classification"],
            "layoutVersion": layout["layoutVersion"],
            "ticket": layout["ticket"],
            "slug": layout["slug"],
            "cloneClassification": "duplicate-clone" if duplicate else "registered",
            "anomalies": sorted(set(anomalies)),
        })
    return {"schema": contract.SCHEMA, "readOnly": True, "entries": entries}


def path_ignored(relative: str, ignore: tuple[str, ...]) -> bool:
    for pattern in ignore:
        if _glob_covers(pattern, relative):
            return True
    return False


def _glob_to_regex(pattern: str) -> str:
    return re.escape(pattern).replace(r"\*\*", "\x00").replace(r"\*", "[^/]*").replace("\x00", ".*")


def _glob_covers(pattern: str, path: str) -> bool:
    if pattern == path:
        return True
    if re.fullmatch(_glob_to_regex(pattern), path):
        return True
    if pattern.endswith("/**"):
        parent = _glob_to_regex(pattern[:-3])
        return re.fullmatch(parent, path) is not None or re.fullmatch(parent + r"/.*", path) is not None
    if pattern.endswith("/*"):
        parent = _glob_to_regex(pattern[:-2])
        return re.fullmatch(parent + r"/[^/]+", path) is not None
    return False


def globs_may_overlap(first: str, second: str) -> bool:
    if first == second:
        return True
    if _glob_covers(first, second.rstrip("*").rstrip("/")) or _glob_covers(
        second, first.rstrip("*").rstrip("/")
    ):
        return True
    first_prefix = first.split("*", 1)[0].rstrip("/")
    second_prefix = second.split("*", 1)[0].rstrip("/")
    if not first_prefix or not second_prefix:
        return True
    return first_prefix == second_prefix or first_prefix.startswith(
        second_prefix + "/"
    ) or second_prefix.startswith(first_prefix + "/")


def default_branch(path: Path) -> str:
    try:
        remote_head = run_git(
            path, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"
        )
        if remote_head.startswith("origin/"):
            return remote_head.removeprefix("origin/")
    except AuditError:
        pass
    for conventional in ("main", "master"):
        try:
            run_git(path, "rev-parse", "--verify", f"refs/heads/{conventional}")
            return conventional
        except AuditError:
            continue
    return "main"


def nul_records(output: str) -> list[str]:
    """Require complete Git -z framing without normalizing path content."""
    if not output:
        return []
    if not output.endswith('\0'):
        raise AuditError('Git path output has an unterminated NUL record')
    records = output.split('\0')[:-1]
    if any(not record for record in records):
        raise AuditError('Git path output contains an empty record')
    return records


def dirty_paths(path: Path, ignore: tuple[str, ...]) -> tuple[str, ...]:
    names: set[str] = set()
    records = iter(nul_records(run_git(
        path, "status", "--porcelain=v1", "-z", "--untracked-files=all")))
    for record in records:
        if (len(record) < 4 or record[2] != ' '
                or any(status not in ' MTADRCU?!' for status in record[:2])):
            raise AuditError('Git status contains a malformed porcelain record')
        names.add(record[3:])
        if 'R' in record[:2] or 'C' in record[:2]:
            # Porcelain -z emits destination, then original path. Both reserve
            # the change, including names with whitespace or a literal arrow.
            original = next(records, None)
            if original is None:
                raise AuditError('Git status is missing a rename/copy source path')
            names.add(original)
    return tuple(sorted(name for name in names if name and not path_ignored(name, ignore)))


def committed_against(
    path: Path, base_ref: str, ignore: tuple[str, ...]
) -> tuple[str, ...]:
    """Paths this checkout has committed since `base_ref`."""
    try:
        raw = run_git(path, "diff", "--name-only", "-z", "--no-renames", f"{base_ref}..HEAD")
    except AuditError:
        return ()
    return tuple(
        sorted(
            {
                line
                for line in nul_records(raw)
                if line and not path_ignored(line, ignore)
            }
        )
    )


def merge_base(path: Path, left: str, right: str) -> str | None:
    try:
        return run_git(path, "merge-base", left, right) or None
    except AuditError:
        return None


def is_ancestor(path: Path, older: str, newer: str) -> bool:
    try:
        run_git(path, "merge-base", "--is-ancestor", older, newer)
        return True
    except AuditError:
        return False


def merge_tree_conflicts(path: Path, left: str, right: str) -> tuple[str, ...] | None:
    """Paths git itself cannot merge, or None when git cannot answer.

    Touching the same path is only a *proxy* for conflicting: two branches often
    edit different regions and merge cleanly, while a stacked branch shares the
    path with its own ancestor and cannot conflict at all. `git merge-tree`
    performs the real merge in memory and reports exactly what breaks, so the
    verdict is ground truth rather than a heuristic. Older git without
    --write-tree returns None and the caller falls back to path intersection.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "merge-tree", "--write-tree", "--name-only", left, right],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
            env=detached_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return ()
    if result.returncode != 1:
        return None
    lines = result.stdout.splitlines()
    conflicted: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            break
        conflicted.append(line.strip())
    return tuple(sorted(set(conflicted)))


def pending_main_imports(path: Path) -> set[str]:
    """Clean staged imports from the current origin default branch, if proven.

    An unfinished merge exposes already integrated main content as index edits.
    It is not a competing contribution. Keep reporting that dirty state, but
    exclude it from overlap attribution only when all local Git reads agree.
    No fetch or index mutation is needed; unknown or older merge heads retain
    conservative behavior. Committed feature edits are never exempted.
    """
    try:
        incoming = run_git(path, "rev-parse", "--verify", "MERGE_HEAD")
        merge_file = Path(run_git(path, "rev-parse", "--path-format=absolute", "--git-path", "MERGE_HEAD"))
        if merge_file.read_text(encoding="ascii").splitlines() != [incoming]:
            return set()  # Octopus merges have more than one source of edits.
        remote = run_git(path, "rev-parse", "--verify",
                         f"refs/remotes/origin/{default_branch(path)}")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", incoming) or incoming != remote:
            return set()
        base = run_git(path, "merge-base", "HEAD", incoming)

        def names(*args: str) -> set[str]:
            return set(run_git(path, *args).split("\0")) - {""}

        staged = names("diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD")
        different = names("diff", "--cached", "--name-only", "--no-renames", "-z", incoming)
        unstaged = names("diff", "--name-only", "--no-renames", "-z")
        untracked = names("ls-files", "--others", "--exclude-standard", "-z")
        local_commits = names("diff", "--name-only", "--no-renames", "-z", base, "HEAD")
        # diff --cached includes unresolved paths; retain an explicit check so
        # equality can never be inferred from a non-stage-zero index entry.
        unresolved = {entry.split("\t", 1)[1]
                      for entry in names("ls-files", "--unmerged", "-z")}
        return staged - different - unstaged - untracked - local_commits - unresolved
    except (AuditError, IndexError, OSError, UnicodeError):
        return set()


def changes_against_shared_default(first, second, first_dirty, second_dirty, first_changes, second_changes):
    shared_default = False
    try:
        first_default = run_git(first.path, "rev-parse", "--verify",
                                f"refs/remotes/origin/{default_branch(first.path)}^{{commit}}")
        second_default = run_git(second.path, "rev-parse", "--verify",
                                 f"refs/remotes/origin/{default_branch(second.path)}^{{commit}}")
        if first_default == second_default:
            first_base = run_git(first.path, "merge-base", first.head, first_default)
            second_base = run_git(second.path, "merge-base", second.head, second_default)
            first_committed = set(run_git(first.path, "diff", "--name-only", "--no-renames", first_base, first.head).splitlines())
            second_committed = set(run_git(second.path, "diff", "--name-only", "--no-renames", second_base, second.head).splitlines())
            first_renames = run_git(first.path, "diff", "--name-only", "--find-renames",
                                    "--diff-filter=R", first_base, first.head)
            second_renames = run_git(second.path, "diff", "--name-only", "--find-renames",
                                     "--diff-filter=R", second_base, second.head)
            # Replace both sides only after every strict Git read succeeds.
            # Rename/directory-rename conflicts can be reported at a path
            # edited under another name. Preserve the conservative path
            # model until attribution can follow those identities too.
            if not first_renames and not second_renames:
                # The default-base comparison removes inherited main changes;
                # it must not reintroduce feature commits shared by both HEADs.
                # Pair-relative paths exclude those commits after strict reads.
                # On unreadable pair history they retain the conservative input.
                first_committed &= first_changes
                second_committed &= second_changes
                first_changes = first_committed | first_dirty
                second_changes = second_committed | second_dirty
                shared_default = True
    except AuditError:
        pass
    return first_changes, second_changes, shared_default


def contested_paths(
    first: "Checkout", second: "Checkout", ignore: tuple[str, ...]
) -> tuple[str, ...]:
    """Paths these two checkouts genuinely contend for.

    Prefer each writer's contribution relative to the same observed origin
    default-branch revision. A pair's older common ancestor includes main's
    history in a fresh writer, even when that writer edits unrelated files.
    Intersect with pair-relative contributions so shared feature history is
    excluded too. Dirty paths and conservative attribution remain independent.
    Missing or divergent observations retain the common-ancestor fallback.
    """
    first_dirty = set(first.dirty_paths) - pending_main_imports(first.path)
    second_dirty = set(second.dirty_paths) - pending_main_imports(second.path)
    first_changes, second_changes = set(first.changed_paths), set(second.changed_paths)
    shared_default = False
    if first.head and second.head:
        base = first.head if first.head == second.head else merge_base(first.path, first.head, second.head)
        if base:
            # Use strict reads here: committed_against's best-effort empty
            # result must not turn an unreadable peer into permission to write.
            try:
                first_committed = set(run_git(first.path, "diff", "--name-only", base, first.head).splitlines())
                second_committed = set(run_git(second.path, "diff", "--name-only", base, second.head).splitlines())
                first_changes = first_committed | first_dirty
                second_changes = second_committed | second_dirty
            except AuditError:
                pass
        first_changes, second_changes, shared_default = changes_against_shared_default(
            first, second, first_dirty, second_dirty, first_changes, second_changes
        )
    dirty_overlap = (first_dirty & second_changes) | (second_dirty & first_changes)
    conflicts: set[str] = set()
    if first.head and second.head and first.head != second.head:
        if not is_ancestor(first.path, first.head, second.head) and not is_ancestor(
            first.path, second.head, first.head
        ):
            reported = merge_tree_conflicts(first.path, first.head, second.head)
            if reported is None:
                # No usable merge-tree: fall back to the path-intersection proxy.
                conflicts = first_changes & second_changes
            else:
                conflicts = set(reported)
                if shared_default:
                    # A branch can conflict with main without contending with
                    # this particular peer. Keep the conflict in its inventory,
                    # but require contributions from both writers for pairing.
                    conflicts &= first_changes & second_changes
    return tuple(
        sorted(
            name
            for name in dirty_overlap | conflicts
            if not path_ignored(name, ignore)
        )
    )


def changed_paths(path: Path, ignore: tuple[str, ...]) -> tuple[str, ...]:
    """Everything this checkout has touched relative to the default branch.

    Used for reporting and for attributing a ticket to the checkout writing it,
    never for deciding whether two checkouts collide.
    """
    names: set[str] = set(dirty_paths(path, ignore))
    branch = default_branch(path)
    base = None
    for candidate in (f"origin/{branch}", branch):
        base = merge_base(path, "HEAD", candidate)
        if base:
            break
    if base:
        names.update(committed_against(path, base, ignore))
    return tuple(sorted(name for name in names if name and not path_ignored(name, ignore)))


def active_statuses(root: Path) -> set[str]:
    for candidate in (root / ".governance/manifest.json", root / "governance/manifest.hub.json"):
        if not candidate.is_file():
            continue
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
            statuses = value["ticket"]["activeStatuses"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise AuditError(f"ticket status registry is invalid: {error}") from error
        if not isinstance(statuses, list) or not statuses or not all(
            isinstance(item, str) and item for item in statuses
        ):
            raise AuditError("ticket status registry has no valid activeStatuses")
        return set(statuses)
    # A repository without the ticket contract still receives physical dirty
    # path protection. It simply contributes no intent-level ticket scopes.
    return set()


def virtual_ticket_files(root):
    storage = run_git(root, "config", "--local", "--default", "files", "--get", "new-project.ticketStorage")
    virtual = None
    if storage == "sqlite":
        try:
            spec = importlib.util.spec_from_file_location("worktree_ticket_input", Path(__file__).with_name("ticket_input.py"))
            module = importlib.util.module_from_spec(spec)
            previous = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                spec.loader.exec_module(module)
            finally:
                sys.dont_write_bytecode = previous
            virtual = {item["ticket"]: item["files"] for item in module.configured_records(root)}
        except Exception as error:
            raise AuditError("configured SQLite ticket scopes are unavailable") from error
    elif storage != "files":
        raise AuditError("unknown ticket storage mode")
    return virtual


def ticket_status_override(virtual, directory):
    override = {}
    if virtual is not None:
        try:
            text = virtual[directory.name]["README.md"][0].decode("utf-8")
            match = re.search(r"(?mi)^-[ \t]+\*\*Status\*\*:[ \t]*([A-Z_]+)[ \t]*$", text)
            if match is None:
                raise ValueError("ticket status missing")
            override = {"status_override": match.group(1)}
        except (KeyError, ValueError) as error:
            raise AuditError("configured SQLite ticket status is invalid") from error
    return override


def scope_intent(directory, virtual):
    intent_path = directory / "intent.json"
    try:
        raw = virtual[directory.name]["intent.json"][0] if virtual is not None else intent_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, KeyError) as error:
        raise AuditError(f"Active ticket intent is unavailable or invalid: {directory.name}") from error
    if not isinstance(value, dict):
        raise AuditError(f"Active ticket intent must be an object: {directory.name}")
    allowed = value.get("allowedPaths")
    conflicts = value.get("conflictsWith", [])
    if not isinstance(allowed, list) or not allowed or not all(
        isinstance(path, str) and path for path in allowed
    ):
        raise AuditError(f"Active ticket intent requires valid allowedPaths: {directory.name}")
    if not isinstance(conflicts, list) or not all(
        isinstance(ticket, str) and ticket for ticket in conflicts
    ):
        raise AuditError(f"Active ticket intent requires valid conflictsWith: {directory.name}")
    return value



def ticket_scope_record(directory, intent):
    allowed = intent.get("allowedPaths")
    conflicts = intent.get("conflictsWith")
    return TicketScope(
        ticket=directory.name,
        workstream=intent.get("workstream") if isinstance(intent.get("workstream"), str) else None,
        allowed_paths=tuple(allowed) if isinstance(allowed, list) else (),
        conflicts_with=tuple(conflicts) if isinstance(conflicts, list) else (),
        path=str(directory.resolve()),
    )

def ticket_scopes(root: Path) -> tuple[tuple[TicketScope, ...], tuple[str, ...]]:
    project = root / "project"
    virtual = virtual_ticket_files(root)
    if virtual is None and not project.is_dir():
        return (), ()
    scopes: list[TicketScope] = []
    errors: list[str] = []
    statuses = active_statuses(root)
    if not statuses:
        return (), ()
    try:
        with ActivityReadBatch(root):
            directories = (project / name for name in virtual) if virtual is not None else project.iterdir()
            for directory in sorted(directories, key=lambda item: item.name):
                if (virtual is None and not directory.is_dir()) or TICKET_DIRECTORY_RE.fullmatch(directory.name) is None:
                    continue
                override = ticket_status_override(virtual, directory)
                try:
                    resolution = resolve_ticket_activity(root, directory, statuses, **override)
                except ActivityError as error:
                    errors.append(f"{directory.name}: {error}")
                    resolution = None
                if resolution is not None and not resolution.active:
                    continue
                try:
                    intent = scope_intent(directory, virtual)
                except AuditError as error:
                    # Keep the checkout and its known identity. The error
                    # fails its audit without blocking an unrelated identity.
                    errors.append(f"{directory.name}: {error}")
                    continue
                scopes.append(ticket_scope_record(directory, intent))
    except ActivityError as error:
        errors.append(str(error))
    return tuple(scopes), tuple(errors)


def has_pending_work(path: Path, dirty: bool) -> bool:
    """Is this checkout actually a writer?

    A checkout whose HEAD is already contained in the default branch, with a
    clean tree, is a leftover — merged and forgotten. It conflicts with nothing
    because it is contributing nothing, and pairing it with live branches buries
    the real findings. Leftovers are workspace_lifecycle_check.py's job.
    """
    if dirty:
        return True
    branch = default_branch(path)
    for candidate in (f"origin/{branch}", branch):
        if merge_base(path, "HEAD", candidate) is None:
            continue
        return not is_ancestor(path, "HEAD", candidate)
    return True


def inspect_checkout(path: Path, ignore: tuple[str, ...]) -> Checkout:
    common = Path(run_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    try:
        head = run_git(path, "rev-parse", "--verify", "HEAD")
    except AuditError:
        head = None
    branch = run_git(path, "branch", "--show-current") or None
    dirty = bool(run_git(path, "status", "--porcelain=v1", "--untracked-files=all"))
    pending = has_pending_work(path, dirty)
    scopes, activity_errors = ticket_scopes(path) if pending else ((), ())
    return Checkout(
        path=path.resolve(),
        common_git_dir=common,
        identity=repository_identity(path),
        head=head,
        branch=branch,
        dirty=dirty,
        pending=pending,
        # A leftover contributes nothing to any merge, so skip the three
        # expensive reads it would only feed into comparisons that are skipped.
        dirty_paths=dirty_paths(path, ignore) if pending else (),
        changed_paths=changed_paths(path, ignore) if pending else (),
        tickets=scopes,
        activity_errors=activity_errors,
    )


def extra_workspace_roots(seed: Path) -> list[Path]:
    roots: list[Path] = []
    for directory in (seed, seed.parent):
        for name in DEFAULT_WORKTREE_DIRNAMES:
            candidate = directory / name
            if candidate.is_dir():
                roots.append(candidate.resolve())
    return roots


def workspace_candidates(workspace_root):
    if not workspace_root.is_dir():
        raise AuditError(f"workspace root is not a directory: {workspace_root}")
    seeds = [workspace_root.resolve(), *extra_workspace_roots(workspace_root)]
    candidate_paths: set[Path] = set()
    for seed in seeds:
        if (seed / ".git").exists():
            candidate_paths.add(seed)
        try:
            children = list(seed.iterdir())
        except OSError as error:
            raise AuditError(f"cannot read {seed}: {error}") from error
        for child in children:
            if not child.is_dir():
                continue
            if (child / ".git").exists():
                candidate_paths.add(child.resolve())
                continue
            try:
                grandchildren = list(child.iterdir())
            except OSError:
                continue
            for grandchild in grandchildren:
                if grandchild.is_dir() and (grandchild / ".git").exists():
                    candidate_paths.add(grandchild.resolve())

    return candidate_paths


def discover_checkouts(workspace_root: Path, ignore: tuple[str, ...]) -> list[Checkout]:
    candidate_paths = workspace_candidates(workspace_root)

    pending = sorted(candidate_paths, key=str)
    inspected: set[Path] = set()
    while pending:
        candidate = pending.pop(0)
        if candidate in inspected:
            continue
        inspected.add(candidate)
        try:
            discovered = {
                worktree
                for worktree in registered_worktrees(candidate)
                if worktree not in candidate_paths
            }
        except AuditError as error:
            raise AuditError(f"Cannot inspect registered worktrees for {candidate}: {error}") from error
        candidate_paths.update(discovered)
        pending.extend(sorted(discovered, key=str))

    checkouts: list[Checkout] = []
    for candidate in sorted(candidate_paths, key=str):
        try:
            checkouts.append(inspect_checkout(candidate, ignore))
        except AuditError as error:
            raise AuditError(f"Cannot inspect checkout {candidate}: {error}") from error
    return checkouts


def conflicts_declared(first: TicketScope, second: TicketScope) -> bool:
    return first.ticket in second.conflicts_with or second.ticket in first.conflicts_with


def optional_code2llm_hint(paths: list[str]) -> dict[str, Any]:
    binary = shutil.which("code2llm")
    if binary is None:
        return {"available": False}
    python_paths = [path for path in paths if path.endswith(".py")]
    return {
        "available": True,
        "binary": binary,
        "pythonOverlapCount": len(python_paths),
        "hint": (
            "code2llm is present; overlapping Python paths can be analyzed with "
            "`code2llm <path> -f toon --fast --no-png --no-chunk`."
        ),
    }


def branch_claims_ticket(branch: str | None, ticket: str) -> bool:
    """True when a checkout's branch is the working branch of this ticket."""
    if not branch:
        return False
    match = TICKET_DIRECTORY_RE.fullmatch(ticket)
    if match is None:
        return False
    number = int(match.group(1))
    return (
        re.search(
            rf"(?:^|[^0-9a-z])ticket[-_/]?0*{number}(?:[^0-9]|$)", branch, re.I
        )
        is not None
    )


def attributed_tickets(group: list[Checkout]) -> dict[Path, tuple[TicketScope, ...]]:
    """Map each checkout to the tickets actually being worked on *there*.

    A merged-but-still-IN_PROGRESS ticket directory is present in every sibling
    worktree of the same repository. Counting it once per checkout would pair a
    ticket against itself through unrelated worktrees and name the wrong ticket
    in the remediation. The working branch is the authority; a ticket whose
    branch is not checked out anywhere falls back to the checkouts that are
    actually writing its directory. If neither signal exists, the ticket is a
    stale unclaimed copy and reserves no checkout scope.
    """
    names = {scope.ticket for checkout in group for scope in checkout.tickets}
    owners: dict[str, set[Path]] = {}
    for name in names:
        claimed = {
            checkout.path
            for checkout in group
            if branch_claims_ticket(checkout.branch, name)
        }
        if not claimed:
            claimed = {
                checkout.path
                for checkout in group
                if any(
                    changed.startswith(f"project/{name}/")
                    for changed in checkout.changed_paths
                )
            }
        owners[name] = claimed
    return {
        checkout.path: tuple(
            scope
            for scope in checkout.tickets
            if checkout.path in owners[scope.ticket]
        )
        for checkout in group
    }


def ticket_pair_findings(first, second, owned, ignore, identity, inventory_by_path, findings):
    for left_ticket in owned[first.path]:
        for right_ticket in owned[second.path]:
            if left_ticket.ticket == right_ticket.ticket:
                continue
            if conflicts_declared(left_ticket, right_ticket):
                continue
            pairs = sorted(
                {
                    f"{left} <-> {right}"
                    for left in left_ticket.allowed_paths
                    for right in right_ticket.allowed_paths
                    if globs_may_overlap(left, right)
                    and not path_ignored(left, ignore)
                    and not path_ignored(right, ignore)
                }
            )
            if not pairs:
                continue
            findings.append(
                Finding(
                    code="GOV-WORKTREE-OVERLAP-002",
                    severity="error",
                    message=(
                        "IN_PROGRESS tickets in sibling worktrees claim overlapping "
                        "allowedPaths without conflictsWith."
                    ),
                    remediation=(
                        "Add conflictsWith on both intents, serialize one ticket to "
                        "BACKLOG/PLAN/BLOCKED, or narrow allowedPaths so they no longer overlap."
                    ),
                    evidence={
                        "identity": identity,
                        "left": str(first.path),
                        "right": str(second.path),
                        "tickets": [left_ticket.ticket, right_ticket.ticket],
                        "overlappingPatterns": pairs,
                        "workspaceClassifications": [
                            inventory_by_path[first.path],
                            inventory_by_path[second.path],
                        ],
                    },
                )
            )


def checkout_pair_findings(first, second, owned, ignore, identity, inventory_by_path, findings):
    shared = list(contested_paths(first, second, ignore))
    if shared:
        findings.append(
            Finding(
                code="GOV-WORKTREE-OVERLAP-001",
                severity="error",
                message=(
                    "Two worktrees of the same repository are changing the same paths."
                ),
                remediation=(
                    "Stop one writer, declare conflictsWith, or move the overlapping "
                    "paths to a single ticket / integration workstream before merge."
                ),
                evidence={
                    "identity": identity,
                    "left": str(first.path),
                    "right": str(second.path),
                    "leftBranch": first.branch,
                    "rightBranch": second.branch,
                    "overlappingPaths": shared,
                    "code2llm": optional_code2llm_hint(shared),
                    "workspaceClassifications": [
                        inventory_by_path[first.path],
                        inventory_by_path[second.path],
                    ],
                },
            )
        )
    ticket_pair_findings(first, second, owned, ignore, identity, inventory_by_path, findings)


def activity_findings(checkouts, only_identity, findings):
    for checkout in checkouts:
        for error in checkout.activity_errors:
            # A repository-level gate must not fail on someone else's policy
            # drift (same contract as the identity-scoped overlap groups below).
            if only_identity is not None and checkout.identity != only_identity:
                continue
            findings.append(Finding(
                code="GOV-TICKET-ACTIVITY-001",
                severity="error",
                message="Ticket activity could not be resolved safely.",
                remediation="Repair active ticket intent or reconcile the clone-external registry from protected evidence; follow error/GOV-TICKET-ACTIVITY.md.",
                evidence={"checkout": str(checkout.path), "detail": error, "fallback": "remain-active"},
            ))


def overlap_findings(
    checkouts: list[Checkout],
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    only_identity: str | None = None,
    focus_checkout: Path | None = None,
    inventory: dict[str, Any] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if inventory is None:
        inventory = workspace_inventory(checkouts)
    if not isinstance(inventory, dict) or not isinstance(inventory.get("entries"), list):
        raise AuditError("Worktrees inventory entries must be an array")
    inventory_by_path = {}
    for entry in inventory["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise AuditError("Worktrees inventory entry must have a path")
        path = Path(entry["path"])
        if path in inventory_by_path:
            raise AuditError(f"Worktrees inventory duplicates {path}")
        inventory_by_path[path] = entry
    for checkout in checkouts:
        if checkout.path not in inventory_by_path:
            raise AuditError(f"Worktrees inventory omitted {checkout.path}")
    activity_findings(checkouts, only_identity, findings)
    groups: dict[str, list[Checkout]] = {}
    for checkout in checkouts:
        groups.setdefault(checkout.identity, []).append(checkout)

    for identity, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        # Sibling repositories still have to be *discovered* — that is how a
        # worktree parked outside its own tree is found — but a repository-level
        # gate must not fail on someone else's conflict.
        if only_identity is not None and identity != only_identity:
            continue
        ordered = sorted(group, key=lambda item: str(item.path))
        owned = attributed_tickets(ordered)
        for index, first in enumerate(ordered):
            if not first.pending:
                continue
            for second in ordered[index + 1 :]:
                if not second.pending:
                    continue
                if focus_checkout is not None and focus_checkout not in {
                    first.path.resolve(),
                    second.path.resolve(),
                }:
                    continue
                checkout_pair_findings(first, second, owned, ignore, identity, inventory_by_path, findings)
    return findings


def report_payload(
    findings: list[Finding],
    checkouts: list[Checkout],
    only_identity: str | None = None,
    inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    groups: dict[str, int] = {}
    for checkout in checkouts:
        groups[checkout.identity] = groups.get(checkout.identity, 0) + 1
    return {
        "schema": REPORT_SCHEMA,
        "status": "passed" if not findings else "failed",
        "scope": only_identity or "workspace",
        "inventory": inventory or {
            "schema": None,
            "readOnly": True,
            "entries": [],
        },
        "summary": {
            "errors": sum(1 for item in findings if item.severity == "error"),
            "warnings": sum(1 for item in findings if item.severity == "warning"),
            "findings": len(findings),
            "checkouts": len(checkouts),
            "pendingCheckouts": sum(1 for item in checkouts if item.pending),
            "identitiesWithMultipleWorktrees": sorted(
                identity for identity, count in groups.items() if count > 1
            ),
        },
        "findings": [asdict(item) for item in findings],
    }


def render_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for finding in payload["findings"]:
        evidence = json.dumps(
            finding["evidence"],
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        lines.append(f"{finding['code']} {finding['severity'].upper()}: {finding['message']} [{evidence}]")
        lines.append(f"  remediation: {finding['remediation']}")
    summary = payload["summary"]
    label = "GOV-WORKTREE-OVERLAP-PASS" if payload["status"] == "passed" else "GOV-WORKTREE-OVERLAP-FAIL"
    identities = ",".join(summary["identitiesWithMultipleWorktrees"]) or "-"
    lines.append(
        f"{label}: {payload['status']} "
        f"({summary['errors']} errors, {summary['warnings']} warnings, "
        f"{summary['checkouts']} checkouts, scope={payload['scope']}, "
        f"multi={identities})"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument(
        "--identity-of",
        type=Path,
        default=None,
        help=(
            "Report only on the repository identity of this checkout. "
            "Use for a repository-level gate; omit for a workspace scan."
        ),
    )
    parser.add_argument(
        "--focus-checkout",
        type=Path,
        default=None,
        help=(
            "Report only conflicts involving this checkout. Use for a local "
            "commit gate; omit for a repository-wide or workspace audit."
        ),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Additional gitignore-style relative path to ignore (repeatable).",
    )
    args = parser.parse_args(argv)

    ignore = tuple(dict.fromkeys((*DEFAULT_IGNORE, *args.ignore)))
    only_identity: str | None = None
    try:
        if args.identity_of is not None:
            only_identity = repository_identity(args.identity_of.expanduser().resolve())
        focus_checkout = (
            args.focus_checkout.expanduser().resolve()
            if args.focus_checkout is not None
            else None
        )
        checkouts = discover_checkouts(args.workspace_root.expanduser().resolve(), ignore)
        inventory = workspace_inventory(checkouts)
        findings = overlap_findings(
            checkouts, ignore, only_identity, focus_checkout, inventory
        )
    except AuditError as error:
        findings = [
            Finding(
                code="GOV-WORKTREE-OVERLAP-003",
                severity="error",
                message="The worktree overlap audit could not be completed safely.",
                remediation="Repair repository metadata or narrow --workspace-root.",
                evidence={"reason": str(error)},
            )
        ]
        checkouts = []
        inventory = {
            "schema": None,
            "readOnly": True,
            "entries": [],
        }

    payload = report_payload(findings, checkouts, only_identity, inventory)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    else:
        print(render_text(payload))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
