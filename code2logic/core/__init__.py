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
from ..fingerprint import (
    ADVISORY_AUTHORITY,
    STRUCTURAL_EXPORT_SCHEMA,
    STRUCTURAL_FINGERPRINT_SCHEMA,
    STRUCTURAL_SIMILARITY_SCHEMA,
    ControlFlowFingerprint,
    DataFlowFingerprint,
    EffectsProfile,
    IOProfile,
    StructuralExportBundle,
    StructuralFingerprint,
    StructuralSimilarityMatch,
    compare_structural_fingerprints,
    export_structural_fingerprints,
    extract_structural_fingerprints_from_source,
    extract_symbol_fingerprint,
    rank_retrieval_candidates,
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
    "ADVISORY_AUTHORITY",
    "STRUCTURAL_EXPORT_SCHEMA",
    "STRUCTURAL_FINGERPRINT_SCHEMA",
    "STRUCTURAL_SIMILARITY_SCHEMA",
    "ControlFlowFingerprint",
    "DataFlowFingerprint",
    "EffectsProfile",
    "IOProfile",
    "StructuralExportBundle",
    "StructuralFingerprint",
    "StructuralSimilarityMatch",
    "compare_structural_fingerprints",
    "export_structural_fingerprints",
    "extract_structural_fingerprints_from_source",
    "extract_symbol_fingerprint",
    "rank_retrieval_candidates",
]
