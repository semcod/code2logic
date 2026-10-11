"""Pytest lifecycle bridge for the adopted wellmanifest governance gate."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


class GovernanceGateError(RuntimeError):
    """Raised when deterministic governance rejects the current checkout."""


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return None
    return result.stdout.strip()


def _activate_managed_hook(root: Path) -> None:
    """Activate the installed clone-local hook before enforcing the gate."""
    contract_path = root / ".governance" / "agent-hosts.json"
    if not contract_path.is_file():
        return
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hook = contract["hook"]
        hook_path = hook["path"]
        hooks_config = hook["hooksPathConfig"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return
    if not all(isinstance(value, str) and value for value in (hook_path, hooks_config)):
        return
    hook_file = Path(hook_path)
    config_path = Path(hooks_config)
    if (
        hook_file.is_absolute()
        or config_path.is_absolute()
        or ".." in hook_file.parts
        or ".." in config_path.parts
        or not (root / hook_file).is_file()
    ):
        return
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", hooks_config],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _github_event_base(root: Path) -> str | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if not event_path:
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        base = event["pull_request"]["base"]["sha"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(base, str) or re.fullmatch(r"[0-9a-f]{40}", base) is None:
        return None
    if _git(root, "cat-file", "-e", f"{base}^{{commit}}") is None:
        subprocess.run(
            ["git", "fetch", "--no-tags", "--depth=1", "origin", base],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    if _git(root, "cat-file", "-e", f"{base}^{{commit}}") is not None:
        return base
    return None


def _resolve_base(root: Path) -> str:
    explicit = os.environ.get("WELLMANIFEST_BASE_SHA", "").strip()
    if explicit and _git(root, "cat-file", "-e", f"{explicit}^{{commit}}") is not None:
        return explicit

    github_event_base = _github_event_base(root)
    if github_event_base:
        return github_event_base

    candidates: list[str] = []
    github_base = os.environ.get("GITHUB_BASE_REF", "").strip()
    if github_base:
        candidates.append(f"origin/{github_base}")
    candidates.append("origin/main")
    for candidate in candidates:
        if _git(root, "rev-parse", "--verify", f"{candidate}^{{commit}}") is None:
            continue
        merge_base = _git(root, "merge-base", "HEAD", candidate)
        if merge_base:
            return merge_base

    raise GovernanceGateError(
        "GOV-PACKAGING-003: cannot resolve Git base; "
        "set WELLMANIFEST_BASE_SHA or fetch the target branch"
    )


def _changed_paths(root: Path, base: str) -> list[str]:
    paths: set[str] = set()
    commands = (
        ("diff", "--name-only", base, "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    for command in commands:
        output = _git(root, *command)
        if output:
            paths.update(line for line in output.splitlines() if line)
    return sorted(paths)


def pytest_sessionstart(session: object) -> None:
    """Run repository governance once before pytest executes product tests."""
    config = getattr(session, "config", None)
    options = getattr(config, "option", None)
    if bool(getattr(options, "collectonly", False)):
        return
    rootpath = getattr(config, "rootpath", Path.cwd())
    root = Path(str(rootpath)).resolve()
    gate_sh = root / "project" / "governance-check.sh"
    gate_bat = root / "project" / "governance-check.bat"
    if not gate_sh.is_file() and not gate_bat.is_file():
        raise GovernanceGateError(
            "GOV-PACKAGING-003: managed governance gate is missing"
        )
    if os.environ.get("WELLMANIFEST_GOVERNANCE_ACTIVE") == "1":
        raise GovernanceGateError("GOV-PACKAGING-003: recursive gate invocation")

    _activate_managed_hook(root)
    base = _resolve_base(root)
    if sys.platform.startswith("win"):
        if gate_bat.is_file():
            command = [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(gate_bat), "--base", base]
        else:
            command = ["bash", str(gate_sh), "--base", base]
    else:
        command = [str(gate_sh), "--base", base]
    for path in _changed_paths(root, base):
        command.extend(("--changed-file", path))

    environment = dict(os.environ)
    environment["WELLMANIFEST_GOVERNANCE_ACTIVE"] = "1"
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode:
        raise GovernanceGateError(
            f"GOV-PACKAGING-003: governance gate failed with exit code {result.returncode}"
        )
