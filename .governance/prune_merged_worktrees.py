#!/usr/bin/env python3
"""Safely identify and prune linked worktrees whose branches are already merged.

Validates that:
1. The worktree is not the primary checkout.
2. The worktree is clean (no uncommitted, modified, or untracked changes).
3. The worktree HEAD is reachable from target branch (default: origin/main or main).
4. After removing the worktree, deletes the released local branch.
5. Runs git worktree prune.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def git_cmd(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def get_worktrees(repo: Path) -> list[dict[str, str]]:
    res = git_cmd(repo, "worktree", "list", "--porcelain")
    if res.returncode != 0:
        raise RuntimeError(f"git worktree list failed: {res.stderr}")

    worktrees: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        parts = line.split(" ", 1)
        key = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        current[key] = val
    if current:
        worktrees.append(current)
    return worktrees


def is_worktree_clean(path: Path) -> bool:
    res = git_cmd(path, "status", "--porcelain")
    return res.returncode == 0 and not res.stdout.strip()


def is_ancestor(repo: Path, commit: str, target: str) -> bool:
    res = git_cmd(repo, "merge-base", "--is-ancestor", commit, target)
    return res.returncode == 0


def prune_merged_worktrees(
    repo: Path, target_branch: str = "main", dry_run: bool = False
) -> dict[str, Any]:
    target_ref = target_branch
    if git_cmd(repo, "rev-parse", "--verify", f"origin/{target_branch}").returncode == 0:
        target_ref = f"origin/{target_branch}"
    elif git_cmd(repo, "rev-parse", "--verify", target_branch).returncode != 0:
        raise ValueError(f"Target branch '{target_branch}' not found in {repo}")

    wts = get_worktrees(repo)
    if not wts:
        return {"pruned": [], "skipped": []}

    pruned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for wt in wts[1:]:
        wt_path = Path(wt.get("worktree", ""))
        wt_head = wt.get("HEAD", "")
        wt_branch_raw = wt.get("branch", "")
        branch_name = wt_branch_raw.removeprefix("refs/heads/") if wt_branch_raw else None

        if not wt_path.exists():
            skipped.append({"path": str(wt_path), "reason": "directory missing"})
            continue

        if not is_worktree_clean(wt_path):
            skipped.append(
                {
                    "path": str(wt_path),
                    "branch": branch_name,
                    "reason": "dirty (uncommitted changes)",
                }
            )
            continue

        if not is_ancestor(repo, wt_head, target_ref):
            skipped.append(
                {
                    "path": str(wt_path),
                    "branch": branch_name,
                    "head": wt_head,
                    "reason": f"not merged into {target_ref}",
                }
            )
            continue

        if dry_run:
            pruned.append({"path": str(wt_path), "branch": branch_name, "action": "would_remove"})
        else:
            rm_res = git_cmd(repo, "worktree", "remove", str(wt_path))
            if rm_res.returncode != 0:
                skipped.append(
                    {
                        "path": str(wt_path),
                        "branch": branch_name,
                        "reason": f"remove failed: {rm_res.stderr.strip()}",
                    }
                )
                continue

            if branch_name:
                del_res = git_cmd(repo, "branch", "-d", branch_name)
                if del_res.returncode != 0:
                    git_cmd(repo, "branch", "-D", branch_name)

            pruned.append({"path": str(wt_path), "branch": branch_name, "action": "removed"})

    if not dry_run and pruned:
        git_cmd(repo, "worktree", "prune")

    return {"target": target_ref, "pruned": pruned, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prune linked worktrees that are clean and already merged."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Path to repository (default: current directory)",
    )
    parser.add_argument(
        "--target-branch", default="main", help="Target branch to check ancestry against (default: main)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be pruned without changing anything"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args(argv)

    try:
        report = prune_merged_worktrees(
            args.repo.resolve(), target_branch=args.target_branch, dry_run=args.dry_run
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Target branch: {report['target']}")
        print(f"Pruned ({len(report['pruned'])}):")
        for item in report["pruned"]:
            print(f"  - {item['path']} ({item.get('branch', 'detached')}) -> {item['action']}")
        print(f"Skipped ({len(report['skipped'])}):")
        for item in report["skipped"]:
            print(f"  - {item['path']} ({item.get('branch', 'detached')}): {item['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
