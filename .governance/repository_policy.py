#!/usr/bin/env python3
"""Repository delivery profiles and external ticket adapters.

The adoption profile (which standards are installed) and the delivery profile
(how a repository records and publishes work) are separate contracts.  This
module contains the small, host-agnostic part shared by the managed gate and
the pre-commit hook.
"""

from __future__ import annotations

import json
import re
import argparse
import subprocess
from pathlib import Path
from typing import Any


PROFILES = {
    "ticket-worktree": {
        "deliveryMode": "ticket-branch",
        "checkout": "linked-worktree",
        "backend": "files",
        "enforcement": "enforce",
    },
    "main-only-planfile": {
        "deliveryMode": "main-only",
        "checkout": "primary",
        "backend": "planfile",
        "enforcement": "enforce",
    },
    "main-only-files": {
        "deliveryMode": "main-only",
        "checkout": "primary",
        "backend": "files",
        "enforcement": "enforce",
    },
    "protected-pr": {
        "deliveryMode": "ticket-branch",
        "checkout": "linked-worktree",
        "backend": "files",
        "enforcement": "enforce",
    },
    "local-audit": {
        "deliveryMode": "main-only",
        "checkout": "primary",
        "backend": "files",
        "enforcement": "audit",
    },
}


def default_policy() -> dict[str, Any]:
    return {
        "profile": "ticket-worktree",
        "enforcement": "enforce",
        "delivery": {
            "mode": "ticket-branch",
            "checkout": "linked-worktree",
            "targetBranches": ["main"],
        },
        "tickets": {
            "backend": "files",
            "idPattern": r"^ticket-[0-9]{3,}$",
            "referenceRequired": True,
        },
    }


def selected_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    value = manifest.get("repositoryPolicy")
    if value is None:
        return default_policy()
    return value


def relative_path_error(value: Any, *, pattern: bool = False) -> str | None:
    """Reject paths that can escape the repository or hide a traversal."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return "path must be a non-empty string"
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return "path must be repository-relative"
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return "path contains an unsafe component"
    if not pattern and any(char in normalized for char in "*?["):
        return "exact path must not contain glob metacharacters"
    return None


def _read_index_bytes(root: Path, raw_path: str) -> bytes | None:
    """Read the path that will be committed, not the mutable working tree."""
    result = subprocess.run(
        ["git", "show", f":{raw_path}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _index_has_symlink(root: Path, raw_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", raw_path],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return any(line.split(maxsplit=1)[0] == "120000" for line in result.stdout.splitlines() if line)


def _working_tree_has_symlink(root: Path, raw_path: str) -> bool:
    current = root
    for part in Path(raw_path).parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _snapshot_bytes(root: Path, raw_path: str, *, staged: bool) -> bytes | None:
    if staged:
        return _read_index_bytes(root, raw_path)
    path = root / raw_path
    try:
        return path.read_bytes()
    except (OSError, UnicodeError):
        return None


def _safe_snapshot_path(root: Path, raw_path: str, *, staged: bool) -> str | None:
    error = relative_path_error(raw_path)
    if error:
        return error
    if _index_has_symlink(root, raw_path) if staged else _working_tree_has_symlink(root, raw_path):
        return "path contains a symlink"
    try:
        repository = root.resolve()
        resolved = (root / raw_path).resolve(strict=False)
    except OSError as error:
        return f"path cannot be resolved: {error}"
    if resolved != repository and repository not in resolved.parents:
        return "path resolves outside the repository"
    return None


def policy_error(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "repositoryPolicy must be an object"
    fields = {"profile", "enforcement", "delivery", "tickets"}
    if set(value) != fields:
        return "repositoryPolicy fields must be profile, enforcement, delivery and tickets"
    profile = value.get("profile")
    if profile not in PROFILES:
        return f"unknown repository delivery profile: {profile}"
    if value.get("enforcement") not in {"audit", "enforce"}:
        return "repositoryPolicy enforcement must be audit or enforce"
    delivery = value.get("delivery")
    if not isinstance(delivery, dict) or set(delivery) != {"mode", "checkout", "targetBranches"}:
        return "repositoryPolicy.delivery fields are invalid"
    if delivery.get("mode") not in {"ticket-branch", "main-only"}:
        return "repositoryPolicy.delivery.mode is invalid"
    if delivery.get("checkout") not in {"linked-worktree", "primary"}:
        return "repositoryPolicy.delivery.checkout is invalid"
    branches = delivery.get("targetBranches")
    if not isinstance(branches, list) or not branches or len(branches) != len(set(branches)):
        return "repositoryPolicy.delivery.targetBranches must be unique and non-empty"
    if not all(isinstance(item, str) and item and "/" not in item for item in branches):
        return "repositoryPolicy.delivery.targetBranches contains an invalid branch"
    tickets = value.get("tickets")
    if not isinstance(tickets, dict):
        return "repositoryPolicy.tickets must be an object"
    allowed = {"backend", "idPattern", "referenceRequired", "adapterPath", "sourcePaths"}
    if set(tickets) - allowed or not {"backend", "idPattern", "referenceRequired"} <= set(tickets):
        return "repositoryPolicy.tickets fields are invalid"
    if tickets.get("backend") not in {"files", "sqlite", "planfile"}:
        return "repositoryPolicy.tickets.backend is invalid"
    if not isinstance(tickets.get("idPattern"), str) or not tickets["idPattern"]:
        return "repositoryPolicy.tickets.idPattern must be non-empty"
    try:
        re.compile(tickets["idPattern"])
    except re.error as error:
        return f"repositoryPolicy.tickets.idPattern is invalid: {error}"
    if not isinstance(tickets.get("referenceRequired"), bool):
        return "repositoryPolicy.tickets.referenceRequired must be boolean"
    for field in ("adapterPath",):
        if field in tickets and relative_path_error(tickets[field]) is not None:
            return f"repositoryPolicy.tickets.{field} must be a safe repository-relative path"
    if "sourcePaths" in tickets:
        paths = tickets["sourcePaths"]
        if (
            not isinstance(paths, list)
            or not paths
            or any(relative_path_error(item) is not None for item in paths)
        ):
            return "repositoryPolicy.tickets.sourcePaths must be a safe non-empty path list"
    preset = PROFILES[profile]
    if (
        value.get("delivery", {}).get("mode") != preset["deliveryMode"]
        or value.get("delivery", {}).get("checkout") != preset["checkout"]
    ):
        return f"repositoryPolicy profile {profile} does not match its delivery mode"
    if value.get("tickets", {}).get("backend") != preset["backend"]:
        return f"repositoryPolicy profile {profile} does not match its ticket backend"
    if profile != "local-audit" and value.get("enforcement") != preset["enforcement"]:
        return f"repositoryPolicy profile {profile} must use enforcement={preset['enforcement']}"
    if tickets.get("backend") == "planfile" and "adapterPath" not in tickets:
        return "planfile profile requires tickets.adapterPath"
    return None


def load_adapter(
    root: Path,
    manifest: dict[str, Any],
    *,
    staged: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    policy = selected_policy(manifest)
    tickets = policy.get("tickets", {})
    if tickets.get("backend") != "planfile":
        return None, None
    raw_path = tickets.get("adapterPath")
    if not isinstance(raw_path, str) or relative_path_error(raw_path) is not None:
        return None, "planfile adapterPath is missing or unsafe"
    path_error = _safe_snapshot_path(root, raw_path, staged=staged)
    if path_error:
        return None, f"planfile adapterPath is unsafe: {path_error}"
    raw_adapter = _snapshot_bytes(root, raw_path, staged=staged)
    if raw_adapter is None:
        return None, "planfile ticket adapter is unreadable from the selected snapshot"
    try:
        adapter = json.loads(raw_adapter.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return None, f"planfile ticket adapter is unreadable: {error}"
    error = adapter_error(adapter, root, raw_path, tickets, staged=staged)
    return (None, error) if error else (adapter, None)


def adapter_error(
    adapter: Any,
    root: Path,
    raw_path: str,
    tickets: dict[str, Any],
    *,
    staged: bool = False,
) -> str | None:
    fields = {"schema", "ticket", "summary", "status", "workflow", "workstream", "allowedPaths", "forbiddenPaths", "sourcePaths"}
    if not isinstance(adapter, dict) or set(adapter) != fields:
        return "external ticket adapter fields are invalid"
    if adapter.get("schema") != "wellmanifest.external-ticket-adapter/v1":
        return "unsupported external ticket adapter schema"
    ticket = adapter.get("ticket")
    if not isinstance(ticket, str) or re.fullmatch(tickets["idPattern"], ticket) is None:
        return "external ticket adapter has an invalid ticket ID"
    if not isinstance(adapter.get("summary"), str) or not adapter["summary"].strip():
        return "external ticket adapter summary is blank"
    if adapter.get("status") not in {"IN_PROGRESS"} or adapter.get("workflow") not in {"EDIT", "VALIDATION", "PUBLICATION"}:
        return "external ticket adapter is not active"
    if not isinstance(adapter.get("workstream"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", adapter["workstream"]):
        return "external ticket adapter workstream is invalid"
    for field in ("allowedPaths", "forbiddenPaths", "sourcePaths"):
        values = adapter.get(field)
        if not isinstance(values, list) or len(values) != len(set(values)):
            return f"external ticket adapter {field} is invalid"
        for item in values:
            error = relative_path_error(item, pattern=field != "sourcePaths")
            if error:
                return f"external ticket adapter {field} is invalid: {error}"
    if not adapter["allowedPaths"]:
        return "external ticket adapter allowedPaths is empty"
    for source in adapter["sourcePaths"]:
        path_error = _safe_snapshot_path(root, source, staged=staged)
        if path_error:
            return f"external ticket source is unsafe: {source}: {path_error}"
        raw_source = _snapshot_bytes(root, source, staged=staged)
        if raw_source is None:
            return f"external ticket source is missing: {source}"
        observed = None
        try:
            for line in raw_source.decode("utf-8").splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = value.get("event", value) if isinstance(value, dict) else {}
                if isinstance(event, dict) and event.get("ticket_id") == ticket:
                    observed = str(event.get("status", ""))
        except (OSError, UnicodeError) as error:
            return f"external ticket source is unreadable: {error}"
        if observed is None:
            return f"external ticket source does not contain {ticket}: {source}"
        if observed.lower() in {"done", "cancelled", "canceled", "closed"}:
            return f"external ticket {ticket} is terminal in {source}"
    if raw_path in adapter["allowedPaths"] or raw_path in adapter["forbiddenPaths"]:
        return "external ticket adapter cannot own itself"
    return None


def policy_is_main_only(manifest: dict[str, Any]) -> bool:
    return selected_policy(manifest)["delivery"]["mode"] == "main-only"


def policy_requires_reference(manifest: dict[str, Any]) -> bool:
    return bool(selected_policy(manifest)["tickets"].get("referenceRequired"))


def _matches(path: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatchcase
    path_parts = path.replace("\\", "/").strip("/").split("/")

    def match_pattern(pattern: str) -> bool:
        pattern_parts = pattern.replace("\\", "/").strip("/").split("/")
        memo: dict[tuple[int, int], bool] = {}

        def visit(path_index: int, pattern_index: int) -> bool:
            key = (path_index, pattern_index)
            if key in memo:
                return memo[key]
            if pattern_index == len(pattern_parts):
                result = path_index == len(path_parts)
            elif pattern_parts[pattern_index] == "**":
                result = visit(path_index, pattern_index + 1) or (
                    path_index < len(path_parts) and visit(path_index + 1, pattern_index)
                )
            else:
                result = (
                    path_index < len(path_parts)
                    and fnmatchcase(path_parts[path_index], pattern_parts[pattern_index])
                    and visit(path_index + 1, pattern_index + 1)
                )
            memo[key] = result
            return result

        return visit(0, 0)

    return any(match_pattern(pattern) for pattern in patterns)


def check_staged(root: Path) -> tuple[bool, str]:
    manifest_path = ".governance/manifest.json"
    raw_manifest = _read_index_bytes(root, manifest_path)
    if raw_manifest is None:
        return False, "repository manifest is missing from the staged snapshot"
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return False, f"repository manifest is unreadable: {error}"
    error = policy_error(selected_policy(manifest))
    if error:
        return False, error
    policy = selected_policy(manifest)
    if policy["enforcement"] == "audit":
        return True, "repository delivery profile is audit-only"
    branch = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=root,
        check=False, capture_output=True, text=True,
    ).stdout.strip()
    if policy["delivery"]["mode"] == "main-only" and branch not in policy["delivery"]["targetBranches"]:
        return False, f"main-only profile requires one of {policy['delivery']['targetBranches']}, got {branch or 'detached HEAD'}"
    if policy["tickets"]["backend"] == "planfile":
        adapter, error = load_adapter(root, manifest, staged=True)
        if error or adapter is None:
            return False, error or "external ticket adapter is missing"
        raw = subprocess.run(
            [
                "git", "diff", "--cached", "--name-only", "-z", "--no-renames",
                "--diff-filter=ACDMRTUXB", "--",
            ],
            cwd=root, check=False, capture_output=True,
        ).stdout.decode("utf-8", "surrogateescape")
        changed = [item for item in raw.split("\0") if item]
        adapter_path = str(policy["tickets"]["adapterPath"])
        if adapter_path in changed:
            previous = subprocess.run(
                ["git", "show", f"HEAD:{adapter_path}"],
                cwd=root, check=False, capture_output=True,
            )
            if previous.returncode == 0 and previous.stdout != _read_index_bytes(root, adapter_path):
                return False, "ticket adapter changes must be committed separately from delivery files"
        material_policy_path = ".governance/manifest.json"
        manifest_exists_in_head = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{material_policy_path}"],
            cwd=root,
            check=False,
            capture_output=True,
        ).returncode == 0
        if (
            manifest_exists_in_head
            and material_policy_path in changed
            and any(path not in {adapter_path, material_policy_path} for path in changed)
        ):
            return False, "repository delivery policy cannot change with delivery files"
        outside = [
            path for path in changed
            if path not in {adapter_path, material_policy_path}
            and (not _matches(path, adapter["allowedPaths"]) or _matches(path, adapter["forbiddenPaths"]))
        ]
        if outside:
            return False, "staged paths fall outside the active external ticket scope: " + ", ".join(outside)
    return True, "repository delivery profile is valid"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.profile:
        try:
            manifest = json.loads((root / ".governance/manifest.json").read_text(encoding="utf-8"))
            print(selected_policy(manifest)["profile"])
            return 0
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as error:
            print(error)
            return 1
    if args.staged:
        ok, message = check_staged(root)
    else:
        try:
            manifest = json.loads((root / ".governance/manifest.json").read_text(encoding="utf-8"))
            error = policy_error(selected_policy(manifest))
            ok, message = error is None, error or "repository delivery profile is valid"
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            ok, message = False, str(error)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
