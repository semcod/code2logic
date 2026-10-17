"""
Code review utilities.

Automated code analysis for:
- Quality issues (complexity, length)
- Security vulnerabilities
- Performance anti-patterns

Usage:
    from code2logic.code_review import CodeReviewer, analyze_code_quality
"""

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Security patterns to check
SECURITY_PATTERNS = {
    "sql_injection": ["execute", "raw", "cursor.execute"],
    "command_injection": ["os.system", "subprocess.call", "eval", "exec"],
    "path_traversal": ["open(", "Path(", "os.path.join"],
    "hardcoded_secrets": ["password", "secret", "api_key", "token"],
    "insecure_random": ["random.", "randint"],
}

# Performance anti-patterns
PERFORMANCE_PATTERNS = {
    "n_plus_one": ["for.*in.*:", ".all()", ".filter(", ".execute(", "sqlite3.connect("],
    "subprocess_in_loop": [
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.check_output",
        "subprocess.call",
        "run_process",
    ],
    "uncached_parse_in_loop": ["yaml.safe_load", "yaml.load", "ast.parse"],
    "large_memory": ["readlines()", "list(", ".to_list()"],
    "blocking_io": ["requests.get", "urllib.urlopen", "open("],
}

_REGEX_META = re.compile(r"(\.\*|\\[bBsSwWdD]|[\^\$\[\]\|\+\?])")
_LOOP_ONLY_CATEGORIES = {"subprocess_in_loop", "uncached_parse_in_loop"}
_AST_LOOP_TYPES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _pattern_matches(pattern: str, text: str) -> bool:
    """Match pattern against text using regex when regex metacharacters are present."""
    if _REGEX_META.search(pattern):
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error:
            pass
    return pattern.lower() in text.lower()


# Thresholds
COMPLEXITY_HIGH = 15
COMPLEXITY_MEDIUM = 10
LINES_MAX = 50
FILE_LINES_MAX = 500


def analyze_code_quality(project) -> Dict[str, List[Dict]]:
    """Analyze code quality issues.

    Args:
        project: ProjectInfo from analyze_project()

    Returns:
        Dictionary of issues by category
    """
    issues = defaultdict(list)

    for module in project.modules:
        # Complexity analysis
        for func in module.functions:
            if func.complexity > COMPLEXITY_MEDIUM:
                issues["high_complexity"].append(
                    {
                        "path": module.path,
                        "name": func.name,
                        "complexity": func.complexity,
                        "severity": "high"
                        if func.complexity > COMPLEXITY_HIGH
                        else "medium",
                    }
                )

        # Long functions
        for func in module.functions:
            if func.lines > LINES_MAX:
                issues["long_function"].append(
                    {
                        "path": module.path,
                        "name": func.name,
                        "lines": func.lines,
                        "severity": "medium",
                    }
                )

        # Long files
        if module.lines_code > FILE_LINES_MAX:
            issues["long_file"].append(
                {
                    "path": module.path,
                    "lines": module.lines_code,
                    "severity": "low",
                }
            )

        # Missing docstrings
        for func in module.functions:
            if not func.docstring and not func.is_private:
                issues["missing_docstring"].append(
                    {
                        "path": module.path,
                        "name": func.name,
                        "severity": "low",
                    }
                )

        # Class methods
        for cls in module.classes:
            for method in cls.methods:
                if method.complexity > COMPLEXITY_MEDIUM:
                    issues["high_complexity"].append(
                        {
                            "path": module.path,
                            "name": f"{cls.name}.{method.name}",
                            "complexity": method.complexity,
                            "severity": "high"
                            if method.complexity > COMPLEXITY_HIGH
                            else "medium",
                        }
                    )

    return dict(issues)


def check_security_issues(project) -> Dict[str, List[Dict]]:
    """Check for security vulnerabilities.

    Args:
        project: ProjectInfo from analyze_project()

    Returns:
        Dictionary of security issues
    """
    issues = defaultdict(list)

    for module in project.modules:
        # Check imports for dangerous patterns
        for imp in module.imports:
            for category, patterns in SECURITY_PATTERNS.items():
                for pattern in patterns:
                    if pattern.lower() in imp.lower():
                        issues[category].append(
                            {
                                "path": module.path,
                                "import": imp,
                                "severity": "high"
                                if category in ["command_injection", "sql_injection"]
                                else "medium",
                            }
                        )

        # Check function calls
        for func in module.functions:
            for call in func.calls:
                for category, patterns in SECURITY_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.lower() in call.lower():
                            issues[category].append(
                                {
                                    "path": module.path,
                                    "name": func.name,
                                    "call": call,
                                    "severity": "high"
                                    if category
                                    in ["command_injection", "sql_injection"]
                                    else "medium",
                                }
                            )

    return dict(issues)


def _call_name_from_ast(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return f"{node.func.id}("
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            return f"{node.func.value.id}.{node.func.attr}("
        return f".{node.func.attr}("
    return ""


def _resolve_module_source(project, module) -> str:
    source = getattr(module, "source", None) or getattr(module, "content", None)
    if isinstance(source, str) and source:
        return source
    mod_path = getattr(module, "path", "")
    if not mod_path:
        return ""
    candidates = [Path(mod_path)]
    root_path = getattr(project, "root_path", "")
    if root_path:
        candidates.insert(0, Path(root_path) / mod_path)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    return ""


def _scan_ast_loops(module_path: str, source: str, issues: Dict[str, List[Dict]], seen: set) -> None:
    try:
        tree = ast.parse(source, filename=module_path)
    except (SyntaxError, ValueError, RecursionError):
        return

    def record(category: str, func_name: str, call_label: str) -> None:
        key = (category, module_path, func_name, call_label)
        if key not in seen:
            seen.add(key)
            issues[category].append(
                {
                    "path": module_path,
                    "name": func_name,
                    "call": call_label,
                    "severity": "medium",
                }
            )

    def walk(node: ast.AST, func_name: str, in_loop: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            next_name = f"{func_name}.{node.name}" if func_name != "<module>" else node.name
            for child in ast.iter_child_nodes(node):
                walk(child, next_name, False)
            return
        if isinstance(node, ast.ClassDef):
            next_name = node.name
            for child in ast.iter_child_nodes(node):
                walk(child, next_name, False)
            return
        if isinstance(node, ast.Call) and in_loop:
            call_str = _call_name_from_ast(node)
            if call_str:
                for category in ("n_plus_one", "subprocess_in_loop", "uncached_parse_in_loop"):
                    for pattern in PERFORMANCE_PATTERNS.get(category, []):
                        if _pattern_matches(pattern, call_str):
                            record(category, func_name, call_str.rstrip("("))
                            break
        next_loop = in_loop or isinstance(node, _AST_LOOP_TYPES)
        for child in ast.iter_child_nodes(node):
            walk(child, func_name, next_loop)

    walk(tree, "<module>", False)


def check_performance_issues(project) -> Dict[str, List[Dict]]:
    """Check for performance anti-patterns.

    Args:
        project: ProjectInfo from analyze_project()

    Returns:
        Dictionary of performance issues
    """
    issues = defaultdict(list)
    seen = set()

    for module in project.modules:
        source = _resolve_module_source(project, module)
        has_ast = False
        if source and (getattr(module, "language", "python") == "python" or str(module.path).endswith(".py")):
            _scan_ast_loops(module.path, source, issues, seen)
            has_ast = True

        funcs = list(getattr(module, "functions", []))
        for cls in getattr(module, "classes", []):
            for method in getattr(cls, "methods", []):
                funcs.append(method)

        for func in funcs:
            for call in func.calls:
                for category, patterns in PERFORMANCE_PATTERNS.items():
                    if category in _LOOP_ONLY_CATEGORIES and has_ast:
                        continue
                    for pattern in patterns:
                        if _pattern_matches(pattern, call):
                            key = (category, module.path, func.name, call)
                            if key not in seen:
                                seen.add(key)
                                issues[category].append(
                                    {
                                        "path": module.path,
                                        "name": func.name,
                                        "call": call,
                                        "severity": "medium",
                                    }
                                )
                            break

    return dict(issues)



class CodeReviewer:
    """Automated code review with optional LLM enhancement."""

    def __init__(self, client=None):
        """Initialize reviewer.

        Args:
            client: Optional LLM client for enhanced reviews
        """
        self.client = client

    def review(self, project, focus: str = "all") -> Dict[str, Any]:
        """Perform code review.

        Args:
            project: ProjectInfo from analyze_project()
            focus: 'all', 'quality', 'security', 'performance'

        Returns:
            Review results
        """
        results = {
            "summary": {},
            "issues": {},
        }

        if focus in ["all", "quality"]:
            results["issues"]["quality"] = analyze_code_quality(project)

        if focus in ["all", "security"]:
            results["issues"]["security"] = check_security_issues(project)

        if focus in ["all", "performance"]:
            results["issues"]["performance"] = check_performance_issues(project)

        # Calculate summary
        total_issues = 0
        by_severity = {"high": 0, "medium": 0, "low": 0}

        for category_issues in results["issues"].values():
            for issue_list in category_issues.values():
                for issue in issue_list:
                    total_issues += 1
                    sev = issue.get("severity", "medium")
                    by_severity[sev] = by_severity.get(sev, 0) + 1

        results["summary"] = {
            "total_issues": total_issues,
            "by_severity": by_severity,
            "files_analyzed": len(project.modules),
        }

        return results

    def generate_report(
        self, results: Dict[str, Any], project_name: str = "Project"
    ) -> str:
        """Generate markdown review report.

        Args:
            results: Review results from review()
            project_name: Name for the report

        Returns:
            Markdown report
        """
        summary = results["summary"]

        lines = [
            f"# Code Review Report: {project_name}",
            "",
            "## Summary",
            "",
            f"- **Total Issues:** {summary['total_issues']}",
            f"- **High Severity:** {summary['by_severity'].get('high', 0)}",
            f"- **Medium Severity:** {summary['by_severity'].get('medium', 0)}",
            f"- **Low Severity:** {summary['by_severity'].get('low', 0)}",
            f"- **Files Analyzed:** {summary['files_analyzed']}",
            "",
        ]

        for category, category_issues in results["issues"].items():
            if not category_issues:
                continue

            lines.append(f"## {category.title()} Issues")
            lines.append("")

            for issue_type, issues in category_issues.items():
                if not issues:
                    continue

                lines.append(f"### {issue_type.replace('_', ' ').title()}")
                lines.append("")

                for i in issues[:10]:  # Limit to 10 per type
                    sev = (
                        "🔴"
                        if i.get("severity") == "high"
                        else "🟡"
                        if i.get("severity") == "medium"
                        else "🟢"
                    )
                    name = i.get("name", i.get("path", "unknown"))
                    lines.append(f"- {sev} `{i['path']}` - {name}")

                if len(issues) > 10:
                    lines.append(f"- ... and {len(issues) - 10} more")

                lines.append("")

        return "\n".join(lines)
