"""
Refactoring utilities for code2logic.

High-level API for common refactoring tasks:
- Detect duplicates
- Find code quality issues
- Generate refactoring suggestions
- Compare projects

Usage:
    from code2logic.refactor import (
        find_duplicates,
        analyze_quality,
        suggest_refactoring,
        compare_codebases,
    )
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .analyzer import analyze_project
from .code_review import (
    analyze_code_quality,
    check_security_issues,
)
from .llm_clients import BaseLLMClient, get_client


@dataclass
class DuplicateGroup:
    """Group of duplicate functions."""

    hash: str
    functions: List[str]
    suggestion: str
    effort: str = "low"


@dataclass
class RefactoringSuggestion:
    """Single refactoring suggestion."""

    type: str
    severity: str
    location: str
    description: str
    suggestion: str
    effort: str


@dataclass
class RefactoringReport:
    """Complete refactoring analysis report."""

    project_path: str
    total_files: int
    total_functions: int
    duplicates: List[DuplicateGroup] = field(default_factory=list)
    quality_issues: List[RefactoringSuggestion] = field(default_factory=list)
    security_issues: List[RefactoringSuggestion] = field(default_factory=list)
    suggestions: List[RefactoringSuggestion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# Refactoring Report: {self.project_path}",
            "",
            "## Summary",
            f"- **Files:** {self.total_files}",
            f"- **Functions:** {self.total_functions}",
            f"- **Duplicates:** {len(self.duplicates)}",
            f"- **Quality issues:** {len(self.quality_issues)}",
            f"- **Security issues:** {len(self.security_issues)}",
            "",
        ]

        if self.duplicates:
            lines.append("## Duplicates")
            lines.append("")
            for dup in self.duplicates[:10]:
                lines.append(f"### {dup.hash[:8]}")
                lines.append(f"**Suggestion:** {dup.suggestion}")
                lines.append("")
                for func in dup.functions[:5]:
                    lines.append(f"- `{func}`")
                lines.append("")

        if self.quality_issues:
            lines.append("## Quality Issues")
            lines.append("")
            for issue in self.quality_issues[:10]:
                icon = "🔴" if issue.severity == "high" else "🟡"
                lines.append(f"- {icon} **{issue.type}** at `{issue.location}`")
                lines.append(f"  - {issue.description}")
            lines.append("")

        if self.security_issues:
            lines.append("## Security Issues")
            lines.append("")
            for issue in self.security_issues[:10]:
                lines.append(f"- 🔒 **{issue.type}** at `{issue.location}`")
            lines.append("")

        return "\n".join(lines)


def find_duplicates(
    project_path: str,
    threshold: float = 0.8,
) -> List[DuplicateGroup]:
    """Find duplicate functions in a project.

    Args:
        project_path: Path to project
        threshold: Similarity threshold (0-1)

    Returns:
        List of duplicate groups
    """
    project = analyze_project(project_path)

    # Collect all functions
    functions = []
    for module in project.modules:
        for func in module.functions:
            functions.append(
                {
                    "name": func.name,
                    "path": module.path,
                    "signature": f"{func.name}({', '.join(func.params)})",
                    "full_name": f"{module.path}::{func.name}",
                }
            )
        for cls in module.classes:
            for method in cls.methods:
                functions.append(
                    {
                        "name": method.name,
                        "path": module.path,
                        "signature": f"{method.name}({', '.join(method.params)})",
                        "full_name": f"{module.path}::{cls.name}.{method.name}",
                    }
                )

    # Find duplicates by signature
    signature_groups = {}
    for func in functions:
        sig = func["signature"]
        if sig not in signature_groups:
            signature_groups[sig] = []
        signature_groups[sig].append(func["full_name"])

    duplicates = []
    for sig, funcs in signature_groups.items():
        if len(funcs) > 1:
            import hashlib

            hash_ = hashlib.md5(sig.encode()).hexdigest()[:8]
            duplicates.append(
                DuplicateGroup(
                    hash=hash_,
                    functions=funcs,
                    suggestion="Extract to shared utility function",
                    effort="low" if len(funcs) <= 3 else "medium",
                )
            )

    return duplicates


def analyze_quality(
    project_path: str,
    include_security: bool = True,
    include_performance: bool = True,
) -> RefactoringReport:
    """Analyze code quality and generate refactoring report.

    Args:
        project_path: Path to project
        include_security: Include security checks
        include_performance: Include performance checks

    Returns:
        RefactoringReport
    """
    project = analyze_project(project_path)

    # Count functions
    total_functions = sum(
        len(m.functions) + sum(len(c.methods) for c in m.classes)
        for m in project.modules
    )

    report = RefactoringReport(
        project_path=project_path,
        total_files=project.total_files,
        total_functions=total_functions,
    )

    # Find duplicates
    report.duplicates = find_duplicates(project_path)

    # Quality issues
    quality = analyze_code_quality(project)
    for category, issues in quality.items():
        for issue in issues:
            report.quality_issues.append(
                RefactoringSuggestion(
                    type=category,
                    severity=issue.get("severity", "medium"),
                    location=f"{issue.get('path', '')}::{issue.get('name', '')}",
                    description=f"{category}: {issue.get('complexity', issue.get('lines', ''))}",
                    suggestion=f"Refactor to reduce {category}",
                    effort="medium",
                )
            )

    # Security issues
    if include_security:
        security = check_security_issues(project)
        for category, issues in security.items():
            for issue in issues:
                report.security_issues.append(
                    RefactoringSuggestion(
                        type=category,
                        severity=issue.get("severity", "high"),
                        location=f"{issue.get('path', '')}::{issue.get('name', '')}",
                        description=f"Potential {category}",
                        suggestion=f"Review and fix {category}",
                        effort="medium",
                    )
                )

    return report


def suggest_refactoring(
    project_path: str,
    use_llm: bool = False,
    client: BaseLLMClient = None,
) -> RefactoringReport:
    """Generate refactoring suggestions for a project.

    Args:
        project_path: Path to project
        use_llm: Use LLM for detailed suggestions
        client: LLM client (optional)

    Returns:
        RefactoringReport with suggestions
    """
    report = analyze_quality(project_path)

    if use_llm and (client or True):
        try:
            client = client or get_client()

            # Prepare context
            context = f"""Project: {project_path}
Files: {report.total_files}
Functions: {report.total_functions}
Duplicates: {len(report.duplicates)}
Quality issues: {len(report.quality_issues)}
"""

            prompt = f"""Based on this code analysis, provide 3-5 specific refactoring suggestions:

{context}

Issues found:
- {len(report.duplicates)} duplicate function groups
- {len(report.quality_issues)} quality issues

Provide actionable suggestions with:
1. What to refactor
2. Why
3. How
4. Effort estimate (low/medium/high)"""

            response = client.generate(
                prompt,
                system="You are a senior software architect. Provide concise, actionable refactoring suggestions.",
                max_tokens=1000,
            )

            # Parse suggestions (simplified)
            report.suggestions.append(
                RefactoringSuggestion(
                    type="llm_suggestion",
                    severity="info",
                    location="project-wide",
                    description="LLM-generated suggestions",
                    suggestion=response[:500],
                    effort="varies",
                )
            )

        except Exception:
            pass

    return report


def compare_codebases(
    project1: str,
    project2: str,
) -> Dict[str, Any]:
    """Compare two codebases for similarities and differences.

    Args:
        project1: Path to first project
        project2: Path to second project

    Returns:
        Comparison results
    """
    p1 = analyze_project(project1)
    p2 = analyze_project(project2)

    # Collect elements
    def get_elements(project):
        elements = set()
        for module in project.modules:
            for func in module.functions:
                elements.add(f"func:{func.name}")
            for cls in module.classes:
                elements.add(f"class:{cls.name}")
                for method in cls.methods:
                    elements.add(f"method:{cls.name}.{method.name}")
        return elements

    e1 = get_elements(p1)
    e2 = get_elements(p2)

    common = e1 & e2
    only_in_1 = e1 - e2
    only_in_2 = e2 - e1

    similarity = len(common) / max(len(e1 | e2), 1) * 100

    return {
        "project1": {
            "path": project1,
            "files": p1.total_files,
            "elements": len(e1),
        },
        "project2": {
            "path": project2,
            "files": p2.total_files,
            "elements": len(e2),
        },
        "similarity_percent": round(similarity, 1),
        "common_elements": len(common),
        "only_in_project1": len(only_in_1),
        "only_in_project2": len(only_in_2),
        "common": list(common)[:20],
    }


def quick_analyze(project_path: str) -> Dict[str, Any]:
    """Quick analysis for a project.

    Args:
        project_path: Path to project

    Returns:
        Quick analysis results
    """
    project = analyze_project(project_path)

    # Count elements
    total_classes = sum(len(m.classes) for m in project.modules)
    total_functions = sum(len(m.functions) for m in project.modules)
    total_methods = sum(sum(len(c.methods) for c in m.classes) for m in project.modules)

    # Find complex functions
    complex_funcs = []
    for module in project.modules:
        for func in module.functions:
            if func.complexity > 10:
                complex_funcs.append(f"{module.path}::{func.name}")

    return {
        "project": project.name,
        "files": project.total_files,
        "lines": project.total_lines,
        "classes": total_classes,
        "functions": total_functions,
        "methods": total_methods,
        "languages": project.languages,
        "complex_functions": complex_funcs[:10],
    }
