#!/usr/bin/env python3
"""Run worktree-guard.yaml the way pyqual.yaml / goal.yaml force a pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "wellmanifest.worktree-guard/v1"
DEFAULT_INTERVAL = 60


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

# Emitted by --print-pyqual-stage and consumed by install-worktree-guard.sh.
# Kept here so the runner and the installer cannot drift apart.
PYQUAL_TOOL = {
    "name": "worktree_guard",
    "binary": "python3",
    "command": "python3 .governance/worktree_guard.py --root {workdir} --once",
    "output": "",
    "allow_failure": False,
}
PYQUAL_STAGE = {
    "name": "worktree-overlap",
    "tool": "worktree_guard",
    "optional": False,
}


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is not None:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a mapping")
        return data
    if '"schema"' in text and text.lstrip().startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a mapping")
        return data
    # Fail closed without inventing a second YAML parser.
    raise ValueError(
        "PyYAML is required to read worktree-guard.yaml; install PyYAML or run "
        "worktree_overlap_check.py directly"
    )


def resolve_checker(root: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"checker not found: {explicit}")
        return explicit
    for candidate in (
        root / "scripts" / "worktree_overlap_check.py",
        root / ".governance" / "worktree_overlap_check.py",
        # A workspace root is usually not a repository at all, so the last
        # resort is the checker shipped next to this runner.
        Path(__file__).resolve().parent / "worktree_overlap_check.py",
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("worktree_overlap_check.py is not installed in this repository")


def resolve_config(root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    for candidate in (
        root / "worktree-guard.yaml",
        root / ".governance" / "worktree-guard.yaml",
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("worktree-guard.yaml is missing; copy it from wellmanifest/new-project")


def snapshot(root: Path, extra_roots: list[str]) -> str:
    material: list[str] = []
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            env=detached_git_env(),
        )
        material.append(result.stdout)
    except (OSError, subprocess.TimeoutExpired) as error:
        material.append(str(error))
    for raw in extra_roots:
        candidate = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        if not candidate.is_dir():
            continue
        try:
            names = sorted(entry.name for entry in candidate.iterdir())
        except OSError:
            names = []
        material.append(f"{candidate}:{','.join(names)}")
    return hashlib.sha256("\n".join(material).encode()).hexdigest()


def run_once(
    root: Path,
    config: dict[str, Any],
    output_format: str,
    report: Path | None = None,
    checker_path: Path | None = None,
    scope: str = "auto",
) -> int:
    pipeline = config.get("pipeline", {})
    checker = resolve_checker(root, checker_path)
    command = [
        sys.executable,
        str(checker),
        "--workspace-root",
        str(root),
        "--format",
        "json" if report is not None else output_format,
    ]
    for pattern in pipeline.get("ignore") or []:
        command.extend(("--ignore", str(pattern)))
    # A repository gate answers for its own repository. A workspace scan has no
    # single identity to answer for, so it reports on everything it discovers.
    if scope == "repository" or (scope == "auto" and (root / ".git").exists()):
        command.extend(("--identity-of", str(root)))
        command.extend(("--focus-checkout", str(root)))
    if report is None:
        return subprocess.run(command, check=False, env=detached_git_env()).returncode

    # A scheduled scan has nowhere to print to, so it leaves a machine-readable
    # trail instead. The report is written whatever the verdict is; an empty or
    # stale file is how a broken timer becomes visible.
    result = subprocess.run(
        command, check=False, capture_output=True, text=True, env=detached_git_env()
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    payload = result.stdout.strip() or json.dumps(
        {
            "schema": "new-project.worktree-overlap-report/v1",
            "status": "failed",
            "summary": {"errors": 1, "warnings": 0, "findings": 0, "checkouts": 0},
            "findings": [
                {
                    "code": "GOV-WORKTREE-OVERLAP-003",
                    "severity": "error",
                    "message": "The overlap checker produced no report.",
                    "remediation": "Run the checker directly to see the failure.",
                    "evidence": {"stderr": result.stderr[-2000:]},
                }
            ],
        }
    )
    report.write_text(payload + "\n", encoding="utf-8")
    if output_format == "text":
        print(f"worktree-guard: report written to {report}", flush=True)
    return result.returncode


def watch(
    root: Path,
    config: dict[str, Any],
    output_format: str,
    interval: int,
    report: Path | None = None,
    checker_path: Path | None = None,
    scope: str = "auto",
) -> int:
    pipeline = config.get("pipeline", {})
    extra_roots = list(pipeline.get("detect", {}).get("workspace_roots") or [])
    previous = ""
    while True:
        current = snapshot(root, extra_roots)
        if current != previous:
            previous = current
            print("worktree-guard: change detected, running overlap check", flush=True)
        # The topology fingerprint omits dirty/staged files. Check each interval
        # so edits in existing worktrees cannot leave a stale passing report.
        code = run_once(root, config, output_format, report, checker_path, scope)
        if code != 0:
            print("worktree-guard: overlap check failed", flush=True)
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=0)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write the JSON report here instead of relying on stdout (timers).",
    )
    parser.add_argument(
        "--scope",
        choices=("auto", "repository", "workspace"),
        default="auto",
        help=(
            "auto: report on --root's own repository when it is a checkout, "
            "otherwise on the whole workspace."
        ),
    )
    parser.add_argument(
        "--checker",
        type=Path,
        default=None,
        help="Explicit path to worktree_overlap_check.py.",
    )
    parser.add_argument(
        "--print-pyqual-stage",
        action="store_true",
        help="Print the pyqual.yaml custom_tool + stage that runs this guard.",
    )
    args = parser.parse_args(argv)

    if args.print_pyqual_stage:
        print(
            json.dumps(
                {"custom_tools": [PYQUAL_TOOL], "stages": [PYQUAL_STAGE]},
                indent=2,
            )
        )
        return 0

    root = args.root.expanduser().resolve()
    config_path = resolve_config(root, args.config)
    config = load_yaml(config_path)
    if config.get("schema") != SCHEMA:
        print(f"unsupported worktree-guard schema: {config.get('schema')}", file=sys.stderr)
        return 2

    pipeline = config.get("pipeline") or {}
    triggers = pipeline.get("triggers") or []
    configured_interval = DEFAULT_INTERVAL
    for trigger in triggers:
        if trigger.get("kind") == "interval" and isinstance(trigger.get("seconds"), int):
            configured_interval = trigger["seconds"]

    report = args.report.expanduser().resolve() if args.report else None
    checker_path = args.checker.expanduser().resolve() if args.checker else None
    if args.watch or args.interval:
        interval = args.interval or configured_interval
        return watch(
            root, config, args.format, interval, report, checker_path, args.scope
        )
    return run_once(root, config, args.format, report, checker_path, args.scope)


if __name__ == "__main__":
    raise SystemExit(main())
