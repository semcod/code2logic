"""Unit tests for code2logic.code_review performance anti-pattern detection."""

import tempfile
from pathlib import Path

from code2logic.code_review import _pattern_matches, check_performance_issues
from code2logic.models import FunctionInfo, ModuleInfo, ProjectInfo


def _make_project(root_path: str, modules: list[ModuleInfo]) -> ProjectInfo:
    return ProjectInfo(
        name="test-project",
        root_path=root_path,
        languages={"python": len(modules)},
        modules=modules,
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=len(modules),
        total_lines=100,
    )


def test_pattern_matches_regex_and_literal():
    assert _pattern_matches("for.*in.*:", "for item in items:")
    assert not _pattern_matches("for.*in.*:", "format_in_place")
    assert _pattern_matches(".filter(", "User.objects.filter(id=1)")
    assert _pattern_matches("list(", "list(items)")


def test_check_performance_issues_ast_loops():
    source = (
        "import ast\n"
        "import sqlite3\n"
        "import subprocess\n"
        "import yaml\n\n"
        "def process_items(db_path, paths):\n"
        "    conn = sqlite3.connect(db_path)\n"
        "    for p in paths:\n"
        "        conn.execute('SELECT * FROM t WHERE path = ?', (str(p),))\n"
        "        subprocess.run(['git', 'log', str(p)], check=False)\n"
        "        yaml.safe_load(p.read_text())\n"
        "    return [ast.parse(p.read_text()) for p in paths]\n"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        mod_file = Path(tmpdir) / "worker.py"
        mod_file.write_text(source, encoding="utf-8")
        module = ModuleInfo(
            path="worker.py",
            language="python",
            functions=[
                FunctionInfo(
                    name="process_items",
                    calls=["sqlite3.connect", "conn.execute", "subprocess.run", "yaml.safe_load", "ast.parse"],
                )
            ],
        )
        project = _make_project(tmpdir, [module])
        issues = check_performance_issues(project)

    assert "n_plus_one" in issues
    assert any(i["name"] == "process_items" and "execute" in i["call"] for i in issues["n_plus_one"])
    assert "subprocess_in_loop" in issues
    assert any(i["name"] == "process_items" and "subprocess.run" in i["call"] for i in issues["subprocess_in_loop"])
    assert "uncached_parse_in_loop" in issues
    calls = {i["call"] for i in issues["uncached_parse_in_loop"]}
    assert "yaml.safe_load" in calls
    assert "ast.parse" in calls
