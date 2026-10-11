#!/usr/bin/env python3
"""Delegate pre-commit standard freshness to Goal's trusted adopter."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


DIAGNOSTIC = "GOV-STANDARD-UPDATE-001"
DEFAULT_UPDATE_POLICY = {
    "enabled": True,
    "trigger": "pre-commit",
    "action": "prepare-and-abort",
    "executor": "goal",
}


def _refuse(message: str, *, returncode: int = 2) -> int:
    print(f"{DIAGNOSTIC}: {message}", file=sys.stderr)
    print(
        "  Install compatible Goal or repair the active standard-adoption "
        "ticket; never bypass the hook.",
        file=sys.stderr,
    )
    return returncode


def _load_update_policy(path: Path) -> dict[str, object]:
    try:
        adoption = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("standard-adoption.json is unreadable or invalid") from error
    if not isinstance(adoption, dict):
        raise ValueError("standard-adoption.json must contain an object")
    updates = adoption.get("updates")
    if updates is None:
        return dict(DEFAULT_UPDATE_POLICY)
    if not isinstance(updates, dict) or set(updates) != set(DEFAULT_UPDATE_POLICY):
        raise ValueError("standard update policy has missing or unknown fields")
    if (
        not isinstance(updates.get("enabled"), bool)
        or updates.get("trigger") != "pre-commit"
        or updates.get("action") != "prepare-and-abort"
        or updates.get("executor") not in {"goal", "koru-goal"}
    ):
        raise ValueError("standard update policy contains unsupported values")
    return updates


def run(
    root: Path,
    ticket: str,
    *,
    goal_executable: str = "goal",
    koru_executable: str = "koru",
) -> int:
    """Run the Goal-owned protocol when this repository has a standard pin."""
    target = root.resolve()
    adoption_path = target / ".governance" / "standard-adoption.json"
    if not adoption_path.is_file():
        return 0
    try:
        policy = _load_update_policy(adoption_path)
    except ValueError as error:
        return _refuse(str(error))
    if not policy["enabled"]:
        return 0

    goal = shutil.which(goal_executable)
    if goal is None:
        return _refuse("Goal is unavailable, so standard freshness cannot be verified")
    goal_arguments = [
        "governance",
        "adopt",
        "--latest",
        "--pre-commit",
        "--target-root",
        str(target),
        "--ticket",
        ticket,
    ]
    if policy["executor"] == "koru-goal":
        koru = shutil.which(koru_executable)
        if koru is None:
            return _refuse(
                "Koru is the configured standard update executor but is unavailable"
            )
        command = [
            koru,
            "goal",
            "--project",
            str(target),
            "--goal-executable",
            goal,
            "--",
            *goal_arguments,
        ]
    else:
        command = [goal, *goal_arguments]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError:
        return _refuse("Goal could not execute the standard update protocol")
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(
            completed.stderr,
            end="" if completed.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    if completed.returncode != 0:
        return _refuse(
            "Goal refused or prepared a standard update; review its evidence before retrying",
            returncode=completed.returncode,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--goal-executable", default="goal")
    parser.add_argument("--koru-executable", default="koru")
    args = parser.parse_args()
    return run(
        args.root,
        args.ticket,
        goal_executable=args.goal_executable,
        koru_executable=args.koru_executable,
    )


if __name__ == "__main__":
    raise SystemExit(main())
