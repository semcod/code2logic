"""Tests for exclude patterns and directory pruning in ProjectAnalyzer."""

import tempfile
from pathlib import Path
from code2logic.analyzer import ProjectAnalyzer


def test_project_analyzer_exclude_directories():
    """Verify that custom exclude patterns exclude directories and files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("def run(): pass\n")
        (root / "vendor").mkdir()
        (root / "vendor" / "lib.py").write_text("def vendored(): pass\n")
        (root / "custom_ignored").mkdir()
        (root / "custom_ignored" / "foo.py").write_text("def foo(): pass\n")

        analyzer = ProjectAnalyzer(
            str(root),
            use_treesitter=False,
            respect_gitignore=False,
            exclude=["custom_ignored", "custom_ignored/**"],
        )
        project = analyzer.analyze()

        module_paths = [m.path for m in project.modules]
        assert any("app.py" in p for p in module_paths)
        assert not any("foo.py" in p for p in module_paths)
        # vendor is in default IGNORE_DIRS
        assert not any("lib.py" in p for p in module_paths)


def test_default_ignore_dirs():
    """Verify default IGNORE_DIRS includes .subactor, .worktrees, etc."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("def main(): pass\n")
        (root / ".subactor").mkdir()
        (root / ".subactor" / "hidden.py").write_text("def sub(): pass\n")
        (root / ".worktrees").mkdir()
        (root / ".worktrees" / "wt.py").write_text("def wt(): pass\n")

        analyzer = ProjectAnalyzer(
            str(root),
            use_treesitter=False,
            respect_gitignore=False,
        )
        project = analyzer.analyze()

        module_paths = [m.path for m in project.modules]
        assert any("main.py" in p for p in module_paths)
        assert not any("hidden.py" in p for p in module_paths)
        assert not any("wt.py" in p for p in module_paths)
