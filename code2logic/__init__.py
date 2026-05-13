"""
Code2Logic - Convert source code to logical representation for LLM analysis.

A Python library that analyzes codebases and generates compact, LLM-friendly
representations with semantic understanding using NLP and AST parsing.

Features:
- Multi-language support (Python, JavaScript, TypeScript, Java, Go, Rust, etc.)
- Tree-sitter AST parsing for 99% accuracy
- NetworkX dependency graph analysis with PageRank
- Rapidfuzz similarity detection for duplicate functions
- NLP-powered intent extraction from function names and docstrings

Example:
    >>> from code2logic import analyze_project, MarkdownGenerator
    >>> project = analyze_project("/path/to/project")
    >>> output = MarkdownGenerator().generate(project)
    >>> print(output)
"""

__version__ = "1.0.48"
__author__ = "Softreck"
__email__ = "info@softreck.dev"
__license__ = "MIT"

from .adaptive import (
    LLM_CAPABILITIES,
    AdaptiveReproducer,
    AdaptiveResult,
    get_llm_capabilities,
)
from .analyzer import (
    ProjectAnalyzer,
    analyze_project,
)
from .base import (
    BaseGenerator,
    BaseParser,
    VerboseMixin,
)
from .benchmark import (
    BenchmarkResult,
    FormatResult,
    ReproductionBenchmark,
    run_benchmark,
)
from .chunked_reproduction import (
    Chunk,
    ChunkedReproducer,
    ChunkedResult,
    ChunkedSpec,
    auto_chunk_reproduce,
    chunk_spec,
    get_llm_limit,
)
from .code_review import (
    CodeReviewer,
    analyze_code_quality,
    check_performance_issues,
    check_security_issues,
)
from .config import Config, get_api_key, get_model, load_env
from .dependency import DependencyAnalyzer
from .errors import (
    AnalysisError,
    AnalysisResult,
    ErrorHandler,
    ErrorSeverity,
    ErrorType,
    create_error_handler,
)
from .file_formats import (
    generate_file_csv,
    generate_file_json,
    generate_file_yaml,
)
from .function_logic import (
    FunctionLogicGenerator,
)
from .generators import (
    CompactGenerator,
    CSVGenerator,
    JSONGenerator,
    MarkdownGenerator,
    YAMLGenerator,
)
from .gherkin import (
    CucumberYAMLGenerator,
    GherkinGenerator,
    StepDefinitionGenerator,
    csv_to_gherkin,
    gherkin_to_test_data,
)
from .intent import EnhancedIntentGenerator

try:
    from .llm_clients import (
        BaseLLMClient,
        LiteLLMClient,
        OllamaLocalClient,
        OpenRouterClient,
        get_client,
    )
except ImportError:
    from typing import Optional as _Optional

    class BaseLLMClient:  # type: ignore[no-redef]
        def generate(
            self, prompt: str, system: _Optional[str] = None, max_tokens: int = 4000
        ) -> str:
            raise ImportError("lolm is required for LLM features")

        def is_available(self) -> bool:
            return False

    class OpenRouterClient(BaseLLMClient):  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError("lolm is required for LLM features")

    class OllamaLocalClient(BaseLLMClient):  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError("lolm is required for LLM features")

    class LiteLLMClient(BaseLLMClient):  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError("lolm is required for LLM features")

    def get_client(*args, **kwargs):  # type: ignore[no-redef]
        raise ImportError("lolm is required for LLM features")


from .llm_profiler import (
    AdaptiveChunker,
    LLMProfile,
    LLMProfiler,
    get_adaptive_chunker,
    get_or_create_profile,
    get_profile,
    load_profiles,
    profile_llm,
    save_profile,
)
from .logicml import (
    LogicMLGenerator,
    LogicMLSpec,
    generate_logicml,
)
from .markdown_format import (
    MarkdownHybridGenerator,
    MarkdownSpec,
    generate_markdown_hybrid,
    generate_file_markdown,
)
from .metrics import (
    FormatMetrics,
    ReproductionMetrics,
    ReproductionResult,
    SemanticMetrics,
    StructuralMetrics,
    TextMetrics,
    analyze_reproduction,
    compare_formats,
)
from .models import (
    ClassInfo,
    DependencyNode,
    FunctionInfo,
    ModuleInfo,
    ProjectInfo,
    TypeInfo,
)
from .parsers import TreeSitterParser, UniversalParser
from .project_reproducer import (
    FileResult,
    ProjectReproducer,
    ProjectResult,
)
from .project_reproducer import (
    reproduce_project as _reproduce_project_from_source,
)
from .prompts import (
    FORMAT_HINTS,
    get_fix_prompt,
    get_reproduction_prompt,
    get_review_prompt,
)
from .quality import (
    QualityAnalyzer,
    QualityIssue,
    QualityReport,
    get_quality_summary,
)
from .quality import (
    analyze_quality as _analyze_quality_from_project,
)
from .refactor import (
    DuplicateGroup,
    RefactoringReport,
    compare_codebases,
    find_duplicates,
    quick_analyze,
    suggest_refactoring,
)
from .refactor import (
    analyze_quality as _analyze_quality_from_path,
)
from .reproducer import (
    FileValidation,
    SpecReproducer,
    SpecValidator,
    validate_files,
)
from .reproducer import (
    ReproductionResult as SpecReproductionResult,
)
from .reproducer import (
    reproduce_project as _reproduce_project_from_spec,
)
from .reproduction import (
    CodeReproducer,
    compare_code,
    extract_code_block,
    generate_file_gherkin,
)
from .schemas import (
    JSONSchema,
    LogicMLSchema,
    MarkdownSchema,
    YAMLSchema,
    validate_json,
    validate_logicml,
    validate_markdown,
    validate_yaml,
)
from .similarity import SimilarityDetector, get_refactoring_suggestions
from .terminal import (
    ShellRenderer,
    get_renderer,
    render,
    set_renderer,
)
from .toon_format import (
    TOONGenerator,
    TOONParser,
    generate_toon,
    parse_toon,
)
from .universal import (
    CodeElement,
    CodeGenerator,
    CodeLogic,
    ElementType,
    Language,
    UniversalReproducer,
    reproduce_file,
)


def analyze_quality(target, *args, **kwargs):
    if isinstance(target, ProjectInfo):
        return _analyze_quality_from_project(target, *args, **kwargs)
    return _analyze_quality_from_path(str(target), *args, **kwargs)


def reproduce_project(source: str, *args, **kwargs):
    src = str(source)
    if src.endswith((".yaml", ".yml", ".json")):
        return _reproduce_project_from_spec(src, *args, **kwargs)
    return _reproduce_project_from_source(src, *args, **kwargs)


__all__ = [
    # Version
    "__version__",
    # Main API
    "analyze_project",
    "ProjectAnalyzer",
    # Models
    "FunctionInfo",
    "ClassInfo",
    "TypeInfo",
    "ModuleInfo",
    "DependencyNode",
    "ProjectInfo",
    # Generators
    "MarkdownGenerator",
    "CompactGenerator",
    "JSONGenerator",
    "YAMLGenerator",
    "CSVGenerator",
    # Gherkin/BDD
    "GherkinGenerator",
    "StepDefinitionGenerator",
    "CucumberYAMLGenerator",
    "csv_to_gherkin",
    "gherkin_to_test_data",
    # Components
    "EnhancedIntentGenerator",
    "TreeSitterParser",
    "UniversalParser",
    "DependencyAnalyzer",
    "SimilarityDetector",
    # Configuration
    "Config",
    "load_env",
    "get_api_key",
    "get_model",
    # LLM Clients
    "BaseLLMClient",
    "OpenRouterClient",
    "OllamaLocalClient",
    "LiteLLMClient",
    "get_client",
    # Reproduction
    "generate_file_gherkin",
    "compare_code",
    "extract_code_block",
    "CodeReproducer",
    # Code Review
    "analyze_code_quality",
    "check_security_issues",
    "check_performance_issues",
    "CodeReviewer",
    # Benchmark
    "ReproductionBenchmark",
    "run_benchmark",
    "FormatResult",
    "BenchmarkResult",
    # File Formats
    "generate_file_csv",
    "generate_file_json",
    "generate_file_yaml",
    # Adaptive
    "AdaptiveReproducer",
    "AdaptiveResult",
    "get_llm_capabilities",
    "LLM_CAPABILITIES",
    # Universal
    "UniversalReproducer",
    "UniversalParser",
    "CodeGenerator",
    "CodeLogic",
    "CodeElement",
    "Language",
    "ElementType",
    "reproduce_file",
    # Project
    "ProjectReproducer",
    "ProjectResult",
    "FileResult",
    "reproduce_project",
    # Refactoring
    "find_duplicates",
    "analyze_quality",
    "suggest_refactoring",
    "compare_codebases",
    "quick_analyze",
    "RefactoringReport",
    "DuplicateGroup",
    # Metrics
    "ReproductionMetrics",
    "ReproductionResult",
    "SpecReproductionResult",
    "TextMetrics",
    "StructuralMetrics",
    "SemanticMetrics",
    "FormatMetrics",
    "analyze_reproduction",
    "compare_formats",
    # Base
    "VerboseMixin",
    "BaseParser",
    "BaseGenerator",
    # Markdown Format
    "MarkdownHybridGenerator",
    "MarkdownSpec",
    "generate_markdown_hybrid",
    "generate_file_markdown",
    # LLM Profiler
    "LLMProfiler",
    "LLMProfile",
    "AdaptiveChunker",
    "profile_llm",
    "get_profile",
    "get_or_create_profile",
    "get_adaptive_chunker",
    "load_profiles",
    "save_profile",
    # Terminal Rendering
    "ShellRenderer",
    "render",
    "get_renderer",
    "set_renderer",
    # LogicML
    "LogicMLGenerator",
    "LogicMLSpec",
    "generate_logicml",
    # Function Logic
    "FunctionLogicGenerator",
    # Prompts
    "FORMAT_HINTS",
    "get_reproduction_prompt",
    "get_review_prompt",
    "get_fix_prompt",
    # Schemas
    "validate_yaml",
    "validate_logicml",
    "validate_markdown",
    "validate_json",
    "YAMLSchema",
    "LogicMLSchema",
    "MarkdownSchema",
    "JSONSchema",
    # Quality
    "QualityAnalyzer",
    "QualityReport",
    "QualityIssue",
    "get_quality_summary",
    # Similarity
    "get_refactoring_suggestions",
    # Errors
    "ErrorHandler",
    "ErrorType",
    "ErrorSeverity",
    "AnalysisError",
    "AnalysisResult",
    "create_error_handler",
    # Reproducer
    "SpecReproducer",
    "SpecValidator",
    "FileValidation",
    "validate_files",
    # TOON Format
    "TOONGenerator",
    "TOONParser",
    "generate_toon",
    "parse_toon",
    # Chunked Reproduction
    "ChunkedReproducer",
    "ChunkedResult",
    "ChunkedSpec",
    "Chunk",
    "chunk_spec",
    "auto_chunk_reproduce",
    "get_llm_limit",
]
