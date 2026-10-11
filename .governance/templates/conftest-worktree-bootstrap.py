"""Worktree test bootstrap contract (copy into tests/conftest.py).

Provenance: adapted from autogrammar/hillm after commits 305361a and b8a9f8a.
Coding-agent worktrees often lack .venv and dev-installed CLIs. This
session-scoped autouse fixture fail-closes before tests instead of mid-suite
import errors.

Replace ROOT, REQUIRED_CLIS, and the install command for your repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = ROOT / ".venv" / "bin"
REQUIRED_CLIS = ("your-cli",)  # every console script tests invoke


def _dev_install_complete() -> bool:
    return all((VENV_BIN / cli).is_file() for cli in REQUIRED_CLIS)


def _ensure_dev_install() -> None:
    if _dev_install_complete():
        return
    if not (ROOT / ".venv").is_dir():
        subprocess.run(
            [sys.executable, "-m", "venv", str(ROOT / ".venv")],
            cwd=ROOT,
            check=True,
        )
    subprocess.run(
        ["bash", "packages/install-dev.sh"],  # or project-specific installer
        cwd=ROOT,
        check=True,
    )
    if not _dev_install_complete():
        missing = [cli for cli in REQUIRED_CLIS if not (VENV_BIN / cli).is_file()]
        raise RuntimeError(f"dev install incomplete; missing CLIs: {missing}")


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_project_env() -> None:
    _ensure_dev_install()
    path = os.environ.get("PATH", os.defpath)
    os.environ["PATH"] = f"{VENV_BIN}{os.pathsep}{path}"
