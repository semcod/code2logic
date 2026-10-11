"""Planner, validator and read-only inventory for wellmanifest.worktrees/v5."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA = "wellmanifest.worktrees/v5"
MINIMUM_GIT_VERSION = "2.51.0"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TICKET_RE = re.compile(r"^ticket-([0-9]{3,})$")
STEM_RE = re.compile(r"^(ticket-[0-9]{3,})--([a-z0-9]+(?:-[a-z0-9]+)*)$")
BRANCH_RE = re.compile(r"^(?:refs/heads/)?ticket/([0-9]{3,})-([a-z0-9]+(?:-[a-z0-9]+)*)$")


def _path_type(style: str):
    if style == "posix":
        return PurePosixPath
    if style == "windows":
        return PureWindowsPath
    raise ValueError("pathStyle must be 'posix' or 'windows'")


def _validate_segment(label: str, value: str) -> None:
    if not NAME_RE.fullmatch(value):
        raise ValueError(f"{label} must contain lowercase ASCII words separated by hyphens")


def _validate_repository_name(repository_name: str) -> None:
    if (
        not isinstance(repository_name, str)
        or not repository_name
        or repository_name in {".", ".."}
        or any(character in repository_name for character in ("/", "\\", "\0"))
    ):
        raise ValueError("repositoryName must be an observed repository basename")


def plan(
    *,
    repository: str,
    repository_name: str,
    ticket: str,
    slug: str,
    primary_checkout: str,
    path_style: str = "posix",
) -> dict[str, str]:
    """Return the canonical v5 layout record for one delivery unit."""
    _validate_repository_name(repository_name)
    _validate_segment("slug", slug)
    ticket_match = TICKET_RE.fullmatch(ticket)
    if not ticket_match:
        raise ValueError("ticket must match ticket-NNN with at least three digits")

    path_type = _path_type(path_style)
    primary = path_type(primary_checkout)
    if not primary.is_absolute():
        raise ValueError("primaryCheckout must be absolute")
    stem = f"{ticket}--{slug}"
    worktrees_root = primary / ".worktrees"
    lease_root = primary / ".subactor" / "leases"
    return {
        "schema": SCHEMA,
        "kind": "layout-record",
        "repository": repository,
        "repositoryName": repository_name,
        "ticket": ticket,
        "slug": slug,
        "branch": f"ticket/{ticket_match.group(1)}-{slug}",
        "pathStyle": path_style,
        "primaryCheckout": str(primary),
        "worktreesRoot": str(worktrees_root),
        "worktreePath": str(worktrees_root / stem),
        "leaseRoot": str(lease_root),
        "leasePath": str(lease_root / f"{stem}.json"),
        "linkMode": "relative",
        "minimumGitVersion": MINIMUM_GIT_VERSION,
    }


def validate_layout(record: dict[str, Any]) -> list[str]:
    """Return stable layout errors; an empty list means exact conformance."""
    required = (
        "repository",
        "repositoryName",
        "ticket",
        "slug",
        "primaryCheckout",
        "pathStyle",
    )
    missing = [name for name in required if not isinstance(record.get(name), str)]
    if missing:
        return [f"missing_or_invalid:{name}" for name in missing]
    try:
        expected = plan(
            repository=record["repository"],
            repository_name=record["repositoryName"],
            ticket=record["ticket"],
            slug=record["slug"],
            primary_checkout=record["primaryCheckout"],
            path_style=record["pathStyle"],
        )
    except ValueError as exc:
        return [f"invalid_input:{exc}"]

    errors = []
    for key, expected_value in expected.items():
        if record.get(key) != expected_value:
            errors.append(f"noncanonical:{key}")
    extra = sorted(set(record) - set(expected))
    errors.extend(f"unexpected:{key}" for key in extra)
    return errors


def validate(record: dict[str, Any]) -> list[str]:
    """Validate either public v5 record kind."""
    if record.get("kind") == "layout-record":
        return validate_layout(record)
    if record.get("kind") == "inventory-record":
        return validate_inventory(record)
    return ["invalid_kind"]


def validate_filesystem(record: dict[str, Any]) -> list[str]:
    """Reject symlinks in existing repository-local canonical components."""
    errors = validate_layout(record)
    if errors:
        return errors
    native_style = "windows" if os.name == "nt" else "posix"
    if record["pathStyle"] != native_style:
        return ["filesystem_check_unsupported:pathStyle"]

    primary = Path(record["primaryCheckout"])
    checked: set[Path] = set()
    for field in ("primaryCheckout", "worktreesRoot", "worktreePath", "leaseRoot", "leasePath"):
        target = Path(record[field])
        try:
            relative = target.relative_to(primary)
        except ValueError:
            return [f"filesystem_noncanonical:{field}"]
        current = primary
        candidates = [(current, ".")]
        for part in relative.parts:
            current = current / part
            candidates.append((current, str(current.relative_to(primary))))
        for candidate, relative_name in candidates:
            if candidate in checked:
                continue
            checked.add(candidate)
            if candidate.is_symlink():
                errors.append(f"symlink_component:{field}:{relative_name}")
    return errors


def _git_output(args: list[str], *, cwd: str | Path | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True
    ).stdout


def parse_worktree_porcelain(raw: bytes) -> list[dict[str, Any]]:
    """Parse `git worktree list --porcelain -z` without touching the filesystem."""
    records: list[dict[str, Any]] = []
    for raw_record in raw.split(b"\0\0"):
        if not raw_record:
            continue
        record: dict[str, Any] = {
            "path": None,
            "head": None,
            "branch": None,
            "bare": False,
            "detached": False,
            "locked": False,
            "prunable": False,
        }
        for raw_field in raw_record.split(b"\0"):
            if not raw_field:
                continue
            field = raw_field.decode("utf-8", "surrogateescape")
            key, _, value = field.partition(" ")
            if key == "worktree":
                record["path"] = value
            elif key == "HEAD":
                record["head"] = value
            elif key == "branch":
                record["branch"] = value
            elif key in {"bare", "detached", "locked", "prunable"}:
                record[key] = True
        if isinstance(record["path"], str):
            records.append(record)
    return records


def registered_worktrees(start_path: str) -> list[dict[str, Any]]:
    """Observe Git's registered worktrees; this function performs no repair."""
    raw = _git_output(["-C", start_path, "worktree", "list", "--porcelain", "-z"])
    records = parse_worktree_porcelain(raw)
    if not records:
        raise ValueError("Git returned no registered worktrees")
    return records


def resolve_primary_checkout(start_path: str) -> str:
    """Resolve the primary checkout even when called from a linked worktree."""
    records = registered_worktrees(start_path)
    primary = records[0]
    if primary["bare"]:
        raise ValueError("bare repositories do not have a primary checkout")
    return str(primary["path"])


def _delivery_identity(
    stem: str | None, branch: str | None
) -> tuple[str | None, str | None]:
    if stem:
        stem_match = STEM_RE.fullmatch(stem)
        if stem_match:
            return stem_match.group(1), stem_match.group(2)
    if branch:
        branch_match = BRANCH_RE.fullmatch(branch)
        if branch_match:
            return f"ticket-{branch_match.group(1)}", branch_match.group(2)
    return None, None


def _direct_child_stem(path: PurePath, root: PurePath) -> str | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return relative.name if len(relative.parts) == 1 else None


def _legacy_v1_stem(value, repository_name):
    return value.startswith(f"{repository_name}--") and STEM_RE.fullmatch(
        value[len(repository_name) + 2 :]
    )


def _classify_location(candidate, primary, workspace, repository_name, path_style):
    stem = layout_version = None
    if candidate == primary:
        classification = "primary"
    elif (
        value := _direct_child_stem(candidate, primary / ".worktrees")
    ) and STEM_RE.fullmatch(value):
        classification, layout_version, stem = "canonical-v5", "v5", value
    elif (
        value := _direct_child_stem(candidate, primary / "worktrees")
    ) and STEM_RE.fullmatch(value):
        classification, layout_version, stem = "legacy-v4", "v4", value
    elif (
        value := _direct_child_stem(
            candidate, workspace / ".worktrees" / ".branches" / repository_name
        )
    ) and STEM_RE.fullmatch(value):
        classification, layout_version, stem = "legacy-v3", "v3", value
    elif (
        value := _direct_child_stem(candidate, workspace / ".worktrees" / repository_name)
    ) and STEM_RE.fullmatch(value):
        classification, layout_version, stem = "legacy-v2", "v2", value
    elif (
        value := _direct_child_stem(candidate, workspace / ".worktrees")
    ) and _legacy_v1_stem(value, repository_name):
        classification = "legacy-v1"
        layout_version = "v1"
        stem = value[len(repository_name) + 2 :]
    elif path_style == "posix" and (
        candidate == PurePosixPath("/tmp")
        or PurePosixPath("/tmp") in candidate.parents
    ):
        classification = "system-temp"
    else:
        classification = "unknown"

    return classification, layout_version, stem


def classify_path(
    *,
    path: str,
    primary_checkout: str,
    repository_name: str,
    branch: str | None = None,
    path_style: str = "posix",
) -> dict[str, Any]:
    """Classify one registered path without changing or resolving it."""
    path_type = _path_type(path_style)
    candidate = path_type(path)
    primary = path_type(primary_checkout)
    workspace = primary.parent
    classification, layout_version, stem = _classify_location(candidate, primary, workspace, repository_name, path_style)

    ticket, slug = _delivery_identity(stem, branch)
    normalized_branch = branch.removeprefix("refs/heads/") if branch else None
    return {
        "path": str(candidate),
        "branch": normalized_branch,
        "classification": classification,
        "layoutVersion": layout_version,
        "ticket": ticket,
        "slug": slug,
        "anomalies": [],
    }


def _mark_duplicate_deliveries(entries):
    identity_counts = Counter(
        (entry["ticket"], entry["slug"])
        for entry in entries
        if entry["classification"] != "primary" and entry["ticket"] and entry["slug"]
    )
    branch_counts = Counter(
        entry["branch"]
        for entry in entries
        if entry["classification"] != "primary" and entry["branch"]
    )
    for entry in entries:
        identity = (entry["ticket"], entry["slug"])
        if (
            entry["classification"] != "primary"
            and (
                (entry["ticket"] and identity_counts[identity] > 1)
                or (entry["branch"] and branch_counts[entry["branch"]] > 1)
            )
        ):
            entry["anomalies"].append("duplicate-delivery")


def inventory(
    *,
    repository: str,
    repository_name: str,
    primary_checkout: str,
    registered: Iterable[dict[str, Any]],
    path_style: str = "posix",
) -> dict[str, Any]:
    """Build a deterministic, observation-only inventory record."""
    _validate_repository_name(repository_name)
    path_type = _path_type(path_style)
    primary = path_type(primary_checkout)
    if not primary.is_absolute():
        raise ValueError("primaryCheckout must be absolute")

    entries = []
    for observed in registered:
        path = observed.get("path")
        if not isinstance(path, str):
            raise TypeError("every registered worktree requires a path")
        entry = classify_path(
            path=path,
            primary_checkout=primary_checkout,
            repository_name=repository_name,
            branch=observed.get("branch"),
            path_style=path_style,
        )
        entry.update(
            {
                "head": observed.get("head"),
                "bare": bool(observed.get("bare", False)),
                "detached": bool(observed.get("detached", False)),
                "locked": bool(observed.get("locked", False)),
                "prunable": bool(observed.get("prunable", False)),
            }
        )
        entries.append(entry)

    _mark_duplicate_deliveries(entries)

    classification_counts = Counter(entry["classification"] for entry in entries)
    anomaly_counts = Counter(anomaly for entry in entries for anomaly in entry["anomalies"])
    return {
        "schema": SCHEMA,
        "kind": "inventory-record",
        "repository": repository,
        "repositoryName": repository_name,
        "pathStyle": path_style,
        "primaryCheckout": str(primary),
        "readOnly": True,
        "entries": entries,
        "summary": {
            "total": len(entries),
            "classifications": dict(sorted(classification_counts.items())),
            "anomalies": dict(sorted(anomaly_counts.items())),
        },
    }


def validate_inventory(record: dict[str, Any]) -> list[str]:
    """Validate a generated inventory by deterministically rebuilding it."""
    required = ("repository", "repositoryName", "primaryCheckout", "pathStyle", "entries")
    missing = [name for name in required if name not in record]
    if missing:
        return [f"missing:{name}" for name in missing]
    if not isinstance(record["entries"], list):
        return ["missing_or_invalid:entries"]
    observed = [
        {
            "path": entry.get("path"),
            "head": entry.get("head"),
            "branch": entry.get("branch"),
            "bare": entry.get("bare", False),
            "detached": entry.get("detached", False),
            "locked": entry.get("locked", False),
            "prunable": entry.get("prunable", False),
        }
        for entry in record["entries"]
        if isinstance(entry, dict)
    ]
    try:
        expected = inventory(
            repository=record["repository"],
            repository_name=record["repositoryName"],
            primary_checkout=record["primaryCheckout"],
            registered=observed,
            path_style=record["pathStyle"],
        )
    except (TypeError, ValueError) as exc:
        return [f"invalid_input:{exc}"]
    errors = []
    for key, expected_value in expected.items():
        if record.get(key) != expected_value:
            errors.append(f"noncanonical:{key}")
    extra = sorted(set(record) - set(expected))
    errors.extend(f"unexpected:{key}" for key in extra)
    return errors


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"([0-9]+)\.([0-9]+)\.([0-9]+)", value)
    if not match:
        raise ValueError(f"cannot parse Git version: {value}")
    return tuple(int(part) for part in match.groups())


def feature_probe(
    git: str = "git",
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    *,
    from_worktree: str = ".",
) -> dict[str, Any]:
    """Probe Git in the chosen repository, without mutating caller state."""
    # Hooks and concurrent hosts may inherit selectors for another checkout.
    # The explicit cwd owns this read-only observation, not those selectors.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    context = runner(
        [git, "-C", from_worktree, "rev-parse", "--git-dir"],
        check=False, capture_output=True, env=env,
    )
    context_ok = context.returncode == 0
    version_result = runner([git, "--version"], check=False, capture_output=True, env=env)
    version_text = (version_result.stdout + version_result.stderr).decode(
        "utf-8", "replace"
    ).strip()
    try:
        version_ok = (
            version_result.returncode == 0
            and _version_tuple(version_text) >= _version_tuple(MINIMUM_GIT_VERSION)
        )
    except ValueError:
        version_ok = False

    options: dict[str, bool] = {}
    for command in ("add", "repair"):
        options[command] = False
        if context_ok:
            result = runner(
                [git, "-C", from_worktree, "worktree", command, "-h"],
                check=False, capture_output=True, env=env,
            )
            help_text = (result.stdout + result.stderr).decode("utf-8", "replace")
            options[command] = result.returncode in (0, 129) and "relative-paths" in help_text
    supported = version_ok and all(options.values())
    return {
        "minimumGitVersion": MINIMUM_GIT_VERSION,
        "repositoryContextValid": context_ok,
        "probeError": None if context_ok else "repository_context_unavailable",
        "gitVersion": version_text,
        "versionSupported": version_ok,
        "worktreeAddRelativePaths": options["add"],
        "worktreeRepairRelativePaths": options["repair"],
        "supported": supported,
    }


def _read_json(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    planner = subparsers.add_parser("plan")
    planner.add_argument("--repository", required=True)
    planner.add_argument("--repository-name", required=True)
    planner.add_argument("--ticket", required=True)
    planner.add_argument("--slug", required=True)
    location = planner.add_mutually_exclusive_group(required=True)
    location.add_argument("--primary-checkout")
    location.add_argument("--from-worktree")
    planner.add_argument("--path-style", choices=("posix", "windows"), default="posix")

    validator = subparsers.add_parser("validate")
    validator.add_argument("record", help="JSON file or - for stdin")
    validator.add_argument(
        "--check-filesystem",
        action="store_true",
        help="reject symlinks in existing canonical path components",
    )

    observer = subparsers.add_parser("inventory")
    observer.add_argument("--repository", required=True)
    observer.add_argument("--repository-name", required=True)
    observer.add_argument("--from-worktree", default=".")

    probe = subparsers.add_parser("feature-probe")
    probe.add_argument("--git", default="git")
    probe.add_argument("--from-worktree", default=".",
                       help="Repository to probe; independent of the caller cwd")

    args = parser.parse_args()
    if args.command == "plan":
        if args.from_worktree and args.path_style != ("windows" if os.name == "nt" else "posix"):
            parser.error("--from-worktree requires the native path style")
        primary = args.primary_checkout or resolve_primary_checkout(args.from_worktree)
        record = plan(
            repository=args.repository,
            repository_name=args.repository_name,
            ticket=args.ticket,
            slug=args.slug,
            primary_checkout=primary,
            path_style=args.path_style,
        )
        print(json.dumps(record, indent=2))
        return 0

    if args.command == "validate":
        record = _read_json(args.record)
        errors = validate_filesystem(record) if args.check_filesystem else validate(record)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 1

    if args.command == "inventory":
        primary = resolve_primary_checkout(args.from_worktree)
        record = inventory(
            repository=args.repository,
            repository_name=args.repository_name,
            primary_checkout=primary,
            registered=registered_worktrees(args.from_worktree),
        )
        print(json.dumps(record, indent=2))
        return 0

    result = feature_probe(args.git, from_worktree=args.from_worktree)
    print(json.dumps(result, indent=2))
    return 0 if result["supported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
