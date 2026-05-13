"""Core analysis components.

Re-exports from parent package for backward compatibility.
"""

from ..analyzer import ProjectAnalyzer, analyze_project
from ..dependency import DependencyAnalyzer
from ..errors import (
    AnalysisError,
    AnalysisResult,
    ErrorHandler,
    ErrorSeverity,
    ErrorType,
    create_error_handler,
)
from ..models import (
    ClassInfo,
    DependencyNode,
    FunctionInfo,
    ModuleInfo,
    ProjectInfo,
    TypeInfo,
)

__all__ = [
    "FunctionInfo",
    "ClassInfo",
    "TypeInfo",
    "ModuleInfo",
    "DependencyNode",
    "ProjectInfo",
    "ProjectAnalyzer",
    "analyze_project",
    "DependencyAnalyzer",
    "ErrorSeverity",
    "ErrorType",
    "AnalysisError",
    "AnalysisResult",
    "ErrorHandler",
    "create_error_handler",
]
