#!/usr/bin/env python3
"""Audit a workspace root for temporary checkouts and orphan local branches."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPORT_SCHEMA = "new-project.workspace-lifecycle-report/v1"
MAX_REPOSITORIES = 10_000
SCP_REMOTE_RE = re.compile(r"^(?:[^@/]+@)?([^:/]+):(.+)$")
TICKET_DIRECTORY_RE = re.compile(r"^ticket-([0-9]+)$")


@dataclass(order=True)
class Finding:
    code: str
    severity: str
    message: str
    remediation: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class TicketClaim:
    number: int
    ticket: str | None
    summary: str | None
    workstream: str | None
    path: str


@dataclass(frozen=True)
class LocalBranch:
    name: str
    head: str


@dataclass(frozen=True)
class Checkout:
    path: Path
    common_git_dir: Path
    identity: str
    head: str | None
    branch: str | None
    dirty: bool
    tickets: tuple[TicketClaim, ...]


class AuditError(RuntimeError):
    """The local workspace could not be audited safely."""


def load_worktrees_contract():
    """Load the pinned owner inventory without creating bytecode in the checkout."""
    script = Path(__file__).resolve()
    candidates = (
        script.with_name("worktree_path_check.py"),
        script.parent.parent / "subprojects" / "worktrees" / "conformance.py",
    )
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        raise AuditError("the managed Worktrees conformance module is missing")
    spec = importlib.util.spec_from_file_location("workspace_worktrees_contract", source)
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


def run_git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AuditError(f"git failed for {root}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise AuditError(f"git {' '.join(arguments)} failed for {root}: {detail}")
    return result.stdout.strip()


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
        return f"local-repository:{resolved}"
    local = local_remote_path(resolved, remote)
    if local is not None and (local / ".git").exists():
        return repository_identity(local, visited)
    if local is not None:
        return f"local:{local}"
    return normalized_network_remote(remote)


def checkout_head(path: Path) -> str | None:
    try:
        return run_git(path, "rev-parse", "--verify", "HEAD")
    except AuditError:
        status = run_git(
            path,
            "status",
            "--porcelain=v2",
            "--branch",
            "--untracked-files=no",
        )
        if "# branch.oid (initial)" in status.splitlines():
            return None
        raise


def inspect_checkout(path: Path) -> Checkout:
    common = Path(
        run_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ).resolve()
    head = checkout_head(path)
    branch = run_git(path, "branch", "--show-current") or None
    dirty = bool(run_git(path, "status", "--porcelain=v1", "--untracked-files=all"))
    identity = repository_identity(path)
    tickets = ticket_claims(path)
    return Checkout(
        path=path.resolve(),
        common_git_dir=common,
        identity=identity,
        head=head,
        branch=branch,
        dirty=dirty,
        tickets=tickets,
    )


def ticket_claims(root: Path) -> tuple[TicketClaim, ...]:
    project = root / "project"
    if not project.is_dir():
        return ()
    claims: list[TicketClaim] = []
    for directory in sorted(project.iterdir(), key=lambda item: item.name):
        match = TICKET_DIRECTORY_RE.fullmatch(directory.name)
        if not directory.is_dir() or match is None:
            continue
        intent_path = directory / "intent.json"
        intent: dict[str, Any] = {}
        try:
            value = json.loads(intent_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                intent = value
        except (OSError, json.JSONDecodeError):
            pass
        claims.append(TicketClaim(
            number=int(match.group(1)),
            ticket=intent.get("ticket") if isinstance(intent.get("ticket"), str) else None,
            summary=intent.get("summary") if isinstance(intent.get("summary"), str) else None,
            workstream=(
                intent.get("workstream")
                if isinstance(intent.get("workstream"), str)
                else None
            ),
            path=str(directory.resolve()),
        ))
    return tuple(claims)


def highest_ref_ticket(root: Path) -> int:
    highest = 0
    refs = run_git(
        root,
        "for-each-ref",
        "--format=%(refname)",
        "refs/heads",
        "refs/remotes",
    ).splitlines()
    for ref in refs:
        paths = run_git(root, "ls-tree", "-d", "-r", "--name-only", ref, "--", "project")
        for raw_path in paths.splitlines():
            match = re.fullmatch(r"project/ticket-([0-9]+)", raw_path)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest


def allocation_high_water(common_git_dir: Path) -> tuple[int | None, str | None]:
    state = common_git_dir / "new-project-ticket-high-water"
    if not state.exists():
        return None, None
    try:
        raw = state.read_text(encoding="utf-8").strip()
    except OSError as error:
        return None, str(error)
    if not raw.isdigit():
        return None, "high-water state is not a decimal ticket number"
    return int(raw), None


def allocation_findings(checkouts: list[Checkout]) -> list[Finding]:
    findings: list[Finding] = []
    groups: dict[Path, list[Checkout]] = {}
    for checkout in checkouts:
        groups.setdefault(checkout.common_git_dir, []).append(checkout)

    for common_git_dir, group in sorted(groups.items(), key=lambda item: str(item[0])):
        primary = min(group, key=lambda item: str(item.path))
        ref_highest = highest_ref_ticket(primary.path)
        high_water, state_error = allocation_high_water(common_git_dir)
        reserved_highest = max(ref_highest, high_water or 0)
        if state_error:
            findings.append(Finding(
                code="GOV-TICKET-ALLOCATION-001",
                severity="error",
                message="The clone-wide ticket allocation reservation is unreadable.",
                remediation=(
                    "Stop allocators, preserve every ticket worktree and repair the shared "
                    "high-water state through the managed allocator before assigning a number."
                ),
                evidence={"reason": state_error},
            ))

        claims_by_number: dict[int, list[TicketClaim]] = {}
        for checkout in group:
            for claim in checkout.tickets:
                claims_by_number.setdefault(claim.number, []).append(claim)
                if claim.number > reserved_highest:
                    findings.append(Finding(
                        code="GOV-TICKET-ALLOCATION-001",
                        severity="error",
                        message="A ticket directory is outside the clone-wide reservation.",
                        remediation=(
                            "Do not reuse or rename it automatically. Preserve the worktree, "
                            "classify ownership, then allocate through project/new-ticket.sh."
                        ),
                        evidence={
                            "path": claim.path,
                            "refHighest": ref_highest,
                            "reservedHighWater": high_water,
                            "ticket": f"ticket-{claim.number:03d}",
                        },
                    ))

        for number, claims in sorted(claims_by_number.items()):
            identities = {
                (claim.ticket, claim.summary, claim.workstream)
                for claim in claims
            }
            if len(identities) <= 1:
                continue
            findings.append(Finding(
                code="GOV-TICKET-ALLOCATION-002",
                severity="error",
                message="Linked worktrees assign different intents to the same ticket ID.",
                remediation=(
                    "Stop both writers and preserve both heads. Keep the earlier reserved "
                    "identity, allocate a new ID through project/new-ticket.sh for the other "
                    "workstream, then rebuild its branch without mixing histories."
                ),
                evidence={
                    "claims": [asdict(claim) for claim in sorted(claims, key=lambda item: item.path)],
                    "ticket": f"ticket-{number:03d}",
                },
            ))
    return findings


def registered_worktrees(path: Path) -> list[Path]:
    worktrees: list[Path] = []
    for line in run_git(path, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            worktrees.append(Path(line.removeprefix("worktree ")).resolve())
    return worktrees


def local_branches(path: Path) -> tuple[LocalBranch, ...]:
    branches: list[LocalBranch] = []
    output = run_git(
        path,
        "for-each-ref",
        "--format=%(refname:short)\t%(objectname)",
        "refs/heads",
    )
    for line in output.splitlines():
        name, separator, head = line.partition("\t")
        if not separator or not name or not head:
            raise AuditError(f"local branch inventory is malformed for {path}")
        branches.append(LocalBranch(name=name, head=head))
    return tuple(sorted(branches, key=lambda item: item.name))


def default_branch(path: Path, branches: tuple[LocalBranch, ...]) -> str | None:
    if not branches:
        return None
    try:
        remote_head = run_git(
            path,
            "symbolic-ref",
            "--quiet",
            "--short",
            "refs/remotes/origin/HEAD",
        )
    except AuditError:
        remote_head = ""
    if remote_head.startswith("origin/"):
        return remote_head.removeprefix("origin/")

    names = {branch.name for branch in branches}
    for conventional in ("main", "master"):
        if conventional in names:
            return conventional
    if len(branches) == 1:
        return branches[0].name
    raise AuditError(
        f"default branch cannot be resolved without origin/HEAD for {path}"
    )


def choose_primary(checkouts: list[Checkout]) -> Checkout:
    slug = checkouts[0].identity.rsplit("/", 1)[-1]
    named = [checkout for checkout in checkouts if checkout.path.name.lower() == slug]
    if len(named) == 1:
        return named[0]
    common_owners = [
        checkout
        for checkout in checkouts
        if checkout.common_git_dir == checkout.path / ".git"
    ]
    return min(
        common_owners or checkouts,
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
        primary = choose_primary(group)
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

    authoritative_clone: dict[str, Path] = {
        identity: choose_primary(group).common_git_dir
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


def local_branch_findings(
    checkouts: list[Checkout], allowed: set[Path]
) -> list[Finding]:
    findings: list[Finding] = []
    clone_groups: dict[Path, list[Checkout]] = {}
    for checkout in checkouts:
        clone_groups.setdefault(checkout.common_git_dir, []).append(checkout)

    for _, group in sorted(clone_groups.items(), key=lambda item: str(item[0])):
        primary = choose_primary(group)
        branches = local_branches(primary.path)
        default = default_branch(primary.path, branches)
        checkout_by_branch = {
            checkout.branch: checkout
            for checkout in group
            if checkout.branch is not None
        }
        for branch in branches:
            if branch.name == default:
                continue
            active_checkout = checkout_by_branch.get(branch.name)
            if active_checkout is not None and active_checkout.path in allowed:
                continue
            findings.append(Finding(
                code="GOV-WORKSPACE-LIFECYCLE-004",
                severity="error",
                message="A terminal workspace still contains a non-default local branch.",
                remediation=(
                    "Classify the branch HEAD and preserve unique history. After releasing "
                    "its worktree, delete only this exact disposable local ref; never let "
                    "the checker delete it automatically."
                ),
                evidence={
                    "branch": branch.name,
                    "checkout": (
                        str(active_checkout.path)
                        if active_checkout is not None
                        else None
                    ),
                    "defaultBranch": default,
                    "head": branch.head,
                    "identity": primary.identity,
                    "primary": str(primary.path),
                },
            ))
    return findings


def discover_workspace_repositories(
    workspace_root: Path, allow_empty: bool = False
) -> set[Path]:
    if not workspace_root.is_dir():
        raise AuditError(f"workspace root is not a directory: {workspace_root}")
    candidates: list[Path] = []
    if (workspace_root / ".git").exists():
        candidates.append(workspace_root)
    for child in workspace_root.iterdir():
        if not child.is_dir():
            continue
        if (child / ".git").exists():
            candidates.append(child)
            continue
        for grandchild in child.iterdir():
            if grandchild.is_dir() and (grandchild / ".git").exists():
                candidates.append(grandchild)
    candidate_paths = {candidate.resolve() for candidate in candidates}
    if len(candidate_paths) > MAX_REPOSITORIES:
        raise AuditError(f"workspace contains more than {MAX_REPOSITORIES} repositories")

    pending = sorted(candidate_paths, key=str)
    inspected: set[Path] = set()
    while pending:
        candidate = pending.pop(0)
        if candidate in inspected:
            continue
        inspected.add(candidate)
        discovered = {
            worktree
            for worktree in registered_worktrees(candidate)
            if worktree not in candidate_paths
        }
        candidate_paths.update(discovered)
        if len(candidate_paths) > MAX_REPOSITORIES:
            raise AuditError(
                f"workspace contains more than {MAX_REPOSITORIES} repositories"
            )
        pending.extend(sorted(discovered, key=str))
    if not candidate_paths and not allow_empty:
        raise AuditError(
            f"workspace root contains no Git repositories: {workspace_root}"
        )
    return candidate_paths


def evaluate(
    workspace_root: Path,
    allowed: set[Path],
    allow_empty: bool = False,
    target_repository: Path | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    candidate_paths = discover_workspace_repositories(
        workspace_root, allow_empty=allow_empty
    )
    checkouts = [
        inspect_checkout(candidate) for candidate in sorted(candidate_paths, key=str)
    ]
    inventory = workspace_inventory(checkouts)
    if not inventory["entries"] and not allow_empty:
        raise AuditError(
            f"workspace inventory is empty for workspace root: {workspace_root}"
        )
    if target_repository is not None:
        target_resolved = target_repository.expanduser().resolve()
        target_matched = False
        try:
            target_checkout = inspect_checkout(target_resolved)
            target_matched = any(
                c.path == target_resolved
                or c.common_git_dir == target_checkout.common_git_dir
                for c in checkouts
            )
        except Exception:
            target_matched = any(c.path == target_resolved for c in checkouts)
        if not target_matched:
            raise AuditError(
                f"workspace inventory omitted required target repository: {target_repository}"
            )
    inventory_by_path = {
        Path(entry["path"]): entry for entry in inventory["entries"]
    }
    groups: dict[str, list[Checkout]] = {}
    for checkout in checkouts:
        groups.setdefault(checkout.identity, []).append(checkout)

    findings: list[Finding] = []
    findings.extend(allocation_findings(checkouts))
    findings.extend(local_branch_findings(checkouts, allowed))
    for identity in sorted(groups):
        group = groups[identity]
        if len(group) < 2:
            continue
        primary = choose_primary(group)
        for checkout in sorted(group, key=lambda item: str(item.path)):
            if checkout == primary or checkout.path in allowed:
                continue
            linked = checkout.common_git_dir == primary.common_git_dir
            kind = "linked worktree" if linked else "duplicate clone"
            findings.append(Finding(
                code=(
                    "GOV-WORKSPACE-LIFECYCLE-001"
                    if linked
                    else "GOV-WORKSPACE-LIFECYCLE-002"
                ),
                severity="error",
                message=f"A terminal workspace still contains a {kind}.",
                remediation=(
                    "Verify dirty state and HEAD reachability. Preserve unknown or unique data; "
                    "then remove this exact workspace and its disposable local branch."
                ),
                evidence={
                    "branch": checkout.branch,
                    "dirty": checkout.dirty,
                    "head": checkout.head,
                    "identity": identity,
                    "path": str(checkout.path),
                    "primary": str(primary.path),
                    "workspaceClassification": inventory_by_path[checkout.path],
                },
            ))
    return sorted(
        findings,
        key=lambda item: (
            item.code,
            json.dumps(item.evidence, ensure_ascii=False, sort_keys=True),
        ),
    ), inventory


def report_payload(
    findings: list[Finding], inventory: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "passed" if not findings else "failed",
        "summary": {"errors": len(findings), "warnings": 0, "findings": len(findings)},
        "inventory": inventory,
        "findings": [asdict(item) for item in findings],
    }


def render_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for finding in payload["findings"]:
        evidence = json.dumps(
            finding["evidence"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        lines.append(f"{finding['code']} ERROR: {finding['message']} [{evidence}]")
        lines.append(f"  remediation: {finding['remediation']}")
    summary = payload["summary"]
    label = "GOV-WORKSPACE-PASS" if payload["status"] == "passed" else "GOV-WORKSPACE-FAIL"
    lines.append(
        f"{label}: {payload['status']} "
        f"({summary['errors']} errors, {summary['warnings']} warnings)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", required=True, type=Path)
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        type=Path,
        help="Exact active secondary checkout allowed during this non-terminal audit.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--target-repository",
        "--target-root",
        "--target",
        dest="target_repository",
        default=None,
        type=Path,
        help="Exact target repository checkout that must be covered by the inventory.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        default=False,
        help="Allow empty workspace repository inventory without failing the audit.",
    )
    args = parser.parse_args(argv)

    findings: list[Finding]
    inventory: dict[str, Any]
    try:
        allowed = {path.expanduser().resolve() for path in args.allow}
        target_repo = (
            args.target_repository.expanduser().resolve()
            if args.target_repository
            else None
        )
        findings, inventory = evaluate(
            args.workspace_root.expanduser().resolve(),
            allowed,
            allow_empty=args.allow_empty,
            target_repository=target_repo,
        )
    except AuditError as error:
        findings = [Finding(
            code="GOV-WORKSPACE-LIFECYCLE-003",
            severity="error",
            message="The local workspace audit could not be completed safely.",
            remediation="Repair repository metadata or narrow the explicit workspace root.",
            evidence={"reason": str(error)},
        )]
        inventory = {
            "schema": None,
            "readOnly": True,
            "entries": [],
        }

    payload = report_payload(findings, inventory)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(render_text(payload))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
