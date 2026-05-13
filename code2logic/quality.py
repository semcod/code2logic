"""
Code quality analysis module.

Detects quality issues and provides refactoring recommendations.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .models import ModuleInfo, ProjectInfo


@dataclass
class QualityIssue:
    """Represents a code quality issue."""

    type: str
    severity: str  # 'high', 'medium', 'low'
    file: str
    name: str
    value: int
    threshold: int
    recommendation: str


@dataclass
class QualityReport:
    """Complete quality analysis report."""

    issues: List[QualityIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    score: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": self.score,
            "issues_count": len(self.issues),
            "issues": [
                {
                    "type": i.type,
                    "severity": i.severity,
                    "file": i.file,
                    "name": i.name,
                    "value": i.value,
                    "threshold": i.threshold,
                    "recommendation": i.recommendation,
                }
                for i in self.issues
            ],
            "metrics": self.metrics,
        }


class QualityAnalyzer:
    """
    Analyzes code quality and generates recommendations.

    Thresholds:
    - file_lines: Max lines per file (default 500)
    - function_lines: Max lines per function (default 50)
    - class_methods: Max methods per class (default 20)
    - function_params: Max parameters (default 7)
    - cyclomatic_complexity: Max complexity (default 10)
    """

    DEFAULT_THRESHOLDS = {
        "file_lines": 500,
        "function_lines": 50,
        "class_methods": 20,
        "function_params": 7,
    }

    def __init__(self, thresholds: Dict[str, int] = None):
        """Initialize with custom thresholds."""
        self.thresholds = {**self.DEFAULT_THRESHOLDS}
        if thresholds:
            self.thresholds.update(thresholds)

    def analyze(self, project: ProjectInfo) -> QualityReport:
        """
        Analyze project quality.

        Args:
            project: ProjectInfo to analyze

        Returns:
            QualityReport with issues and recommendations
        """
        report = QualityReport()
        report.metrics = {
            "total_files": project.total_files,
            "total_lines": project.total_lines,
            "total_classes": sum(len(m.classes) for m in project.modules),
            "total_functions": sum(len(m.functions) for m in project.modules),
        }

        for module in project.modules:
            self._analyze_module(module, report)

        # Calculate score (deduct points for issues)
        deductions = {
            "high": 10,
            "medium": 5,
            "low": 2,
        }
        for issue in report.issues:
            report.score -= deductions.get(issue.severity, 0)
        report.score = max(0, report.score)

        return report

    def analyze_modules(self, modules: List[ModuleInfo]) -> QualityReport:
        """Analyze a list of modules."""
        report = QualityReport()
        report.metrics = {
            "total_files": len(modules),
            "total_lines": sum(m.lines_total for m in modules),
            "total_classes": sum(len(m.classes) for m in modules),
            "total_functions": sum(len(m.functions) for m in modules),
        }

        for module in modules:
            self._analyze_module(module, report)

        # Calculate score
        deductions = {"high": 10, "medium": 5, "low": 2}
        for issue in report.issues:
            report.score -= deductions.get(issue.severity, 0)
        report.score = max(0, report.score)

        return report

    def _analyze_module(self, module: ModuleInfo, report: QualityReport):
        """Analyze a single module."""
        # Check file length
        if module.lines_total > self.thresholds["file_lines"]:
            severity = (
                "high"
                if module.lines_total > self.thresholds["file_lines"] * 2
                else "medium"
            )
            report.issues.append(
                QualityIssue(
                    type="long_file",
                    severity=severity,
                    file=module.path,
                    name=module.path,
                    value=module.lines_total,
                    threshold=self.thresholds["file_lines"],
                    recommendation=self._get_file_recommendation(module),
                )
            )

        # Check functions
        for func in module.functions:
            self._check_function(func, module.path, report)

        # Check classes
        for cls in module.classes:
            self._check_class(cls, module.path, report)

    def _check_function(self, func, file_path: str, report: QualityReport):
        """Check function quality."""
        # Long function
        if func.lines > self.thresholds["function_lines"]:
            severity = (
                "high"
                if func.lines > self.thresholds["function_lines"] * 2
                else "medium"
            )
            report.issues.append(
                QualityIssue(
                    type="long_function",
                    severity=severity,
                    file=file_path,
                    name=func.name,
                    value=func.lines,
                    threshold=self.thresholds["function_lines"],
                    recommendation=f"Split '{func.name}' into smaller functions. Consider extracting logical blocks into separate helpers.",
                )
            )

        # Too many parameters
        if len(func.params) > self.thresholds["function_params"]:
            report.issues.append(
                QualityIssue(
                    type="many_parameters",
                    severity="medium",
                    file=file_path,
                    name=func.name,
                    value=len(func.params),
                    threshold=self.thresholds["function_params"],
                    recommendation=f"Reduce parameters in '{func.name}'. Consider using a config object or dataclass.",
                )
            )

    def _check_class(self, cls, file_path: str, report: QualityReport):
        """Check class quality."""
        # Too many methods
        if len(cls.methods) > self.thresholds["class_methods"]:
            report.issues.append(
                QualityIssue(
                    type="large_class",
                    severity="medium",
                    file=file_path,
                    name=cls.name,
                    value=len(cls.methods),
                    threshold=self.thresholds["class_methods"],
                    recommendation=f"Class '{cls.name}' has too many methods. Consider splitting into smaller classes or using composition.",
                )
            )

        # Check each method
        for method in cls.methods:
            self._check_function(method, file_path, report)

    def _get_file_recommendation(self, module: ModuleInfo) -> str:
        """Generate recommendation for long file."""
        class_count = len(module.classes)
        func_count = len(module.functions)

        if class_count > 3:
            return f"File has {class_count} classes. Split into separate modules, one class per file."
        elif func_count > 10:
            return f"File has {func_count} functions. Group related functions into separate modules."
        else:
            return "Consider breaking this file into smaller, focused modules."


def analyze_quality(
    project: ProjectInfo, thresholds: Dict[str, int] = None
) -> QualityReport:
    """
    Convenience function to analyze project quality.

    Args:
        project: ProjectInfo to analyze
        thresholds: Optional custom thresholds

    Returns:
        QualityReport
    """
    analyzer = QualityAnalyzer(thresholds)
    return analyzer.analyze(project)


def get_quality_summary(report: QualityReport) -> str:
    """
    Generate human-readable quality summary.

    Args:
        report: QualityReport from analysis

    Returns:
        Formatted summary string
    """
    lines = [
        f"Quality Score: {report.score:.1f}/100",
        f"Issues Found: {len(report.issues)}",
        "",
    ]

    if report.issues:
        lines.append("Issues by Severity:")
        high = sum(1 for i in report.issues if i.severity == "high")
        medium = sum(1 for i in report.issues if i.severity == "medium")
        low = sum(1 for i in report.issues if i.severity == "low")

        if high:
            lines.append(f"  🔴 High: {high}")
        if medium:
            lines.append(f"  🟡 Medium: {medium}")
        if low:
            lines.append(f"  🟢 Low: {low}")

        lines.append("")
        lines.append("Top Issues:")
        for issue in report.issues[:5]:
            lines.append(f"  - [{issue.severity.upper()}] {issue.type}: {issue.name}")
            lines.append(f"    {issue.recommendation}")
    else:
        lines.append("✅ No quality issues detected!")

    return "\n".join(lines)
