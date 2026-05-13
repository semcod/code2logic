"""
Code review utilities.

Automated code analysis for:
- Quality issues (complexity, length)
- Security vulnerabilities
- Performance anti-patterns

Usage:
    from code2logic.code_review import CodeReviewer, analyze_code_quality
"""

from collections import defaultdict
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
    "n_plus_one": ["for.*in.*:", ".all()", ".filter("],
    "large_memory": ["readlines()", "list(", ".to_list()"],
    "blocking_io": ["requests.get", "urllib.urlopen", "open("],
}

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


def check_performance_issues(project) -> Dict[str, List[Dict]]:
    """Check for performance anti-patterns.

    Args:
        project: ProjectInfo from analyze_project()

    Returns:
        Dictionary of performance issues
    """
    issues = defaultdict(list)

    for module in project.modules:
        for func in module.functions:
            for call in func.calls:
                for category, patterns in PERFORMANCE_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.lower() in call.lower():
                            issues[category].append(
                                {
                                    "path": module.path,
                                    "name": func.name,
                                    "call": call,
                                    "severity": "medium",
                                }
                            )

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
