"""
Standardized Benchmark Result Dataclasses.

Unified result types for all benchmark scenarios:
- File reproduction
- Function reproduction
- Format comparison
- Token efficiency
- Project-level benchmarks

Usage:
    from code2logic.benchmarks.results import (
        BenchmarkResult, FileResult, FunctionResult, FormatResult
    )
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FormatResult:
    """Result for a single format test."""

    format_name: str
    spec_size: int = 0
    spec_tokens: int = 0
    generated_size: int = 0

    # Quality metrics
    score: float = 0.0
    similarity: float = 0.0
    syntax_ok: bool = False
    runs_ok: bool = False

    # Efficiency metrics
    compression_ratio: float = 0.0
    token_efficiency: float = 0.0

    # Timing
    gen_time: float = 0.0

    # Error handling
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FileResult:
    """Result for single file reproduction."""

    file_path: str
    language: str

    # Sizes
    original_size: int = 0
    spec_size: int = 0
    generated_size: int = 0

    # Quality
    score: float = 0.0
    similarity: float = 0.0
    syntax_ok: bool = False
    runs_ok: bool = False

    # Format results (when testing multiple formats)
    format_results: Dict[str, FormatResult] = field(default_factory=dict)

    # Timing
    gen_time: float = 0.0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["format_results"] = {k: v.to_dict() for k, v in self.format_results.items()}
        return d


@dataclass
class FunctionResult:
    """Result for single function reproduction."""

    file_path: str
    function_name: str
    language: str

    # Code
    original_code: str = ""
    reproduced_code: str = ""

    # Quality
    similarity: float = 0.0
    syntax_ok: bool = False

    # Timing
    gen_time: float = 0.0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkResult:
    """Complete benchmark result."""

    benchmark_type: str  # 'file', 'function', 'format', 'project'
    timestamp: str = ""

    # Source info
    source_path: str = ""
    total_files: int = 0
    total_functions: int = 0

    # Aggregate metrics
    avg_score: float = 0.0
    avg_similarity: float = 0.0
    syntax_ok_rate: float = 0.0
    runs_ok_rate: float = 0.0
    failure_rate: float = 0.0

    # Best format (for format comparisons)
    best_format: str = ""
    best_score: float = 0.0

    # Detailed results
    file_results: List[FileResult] = field(default_factory=list)
    function_results: List[FunctionResult] = field(default_factory=list)
    format_results: List[FormatResult] = field(default_factory=list)

    # Per-format aggregates
    format_scores: Dict[str, float] = field(default_factory=dict)

    # LLM info
    provider: str = ""
    model: str = ""

    # Timing
    total_time: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def calculate_aggregates(self):
        """Calculate aggregate metrics from detailed results."""
        # File results – include ALL scores (zeros count as failures)
        if self.file_results:
            all_scores = [r.score for r in self.file_results]
            self.avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            self.failure_rate = (
                sum(1 for s in all_scores if s == 0) / len(all_scores) * 100
            )
            self.syntax_ok_rate = (
                sum(1 for r in self.file_results if r.syntax_ok)
                / len(self.file_results)
                * 100
            )
            self.runs_ok_rate = (
                sum(1 for r in self.file_results if r.runs_ok)
                / len(self.file_results)
                * 100
            )

        # Function results – include ALL similarities
        if self.function_results:
            all_sims = [r.similarity for r in self.function_results]
            self.avg_similarity = sum(all_sims) / len(all_sims) if all_sims else 0

        # Format results
        if self.format_results:
            for r in self.format_results:
                self.format_scores[r.format_name] = r.score

        # Best format (works for both format_results-derived and directly populated format_scores)
        if self.format_scores:
            best = max(self.format_scores.items(), key=lambda x: x[1])
            self.best_format = best[0]
            self.best_score = best[1]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["file_results"] = [r.to_dict() for r in self.file_results]
        d["function_results"] = [r.to_dict() for r in self.function_results]
        d["format_results"] = [r.to_dict() for r in self.format_results]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str):
        """Save result to JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str) -> "BenchmarkResult":
        """Load result from JSON file."""
        data = json.loads(Path(path).read_text())
        # Reconstruct nested objects
        raw_file_results = data.pop("file_results", [])
        file_results = []
        for r in raw_file_results:
            fmt_results_raw = r.pop("format_results", {})
            fr = FileResult(**r)
            fr.format_results = {
                k: FormatResult(**v) if isinstance(v, dict) else v
                for k, v in fmt_results_raw.items()
            }
            file_results.append(fr)
        function_results = [
            FunctionResult(**r) for r in data.pop("function_results", [])
        ]
        format_results = [FormatResult(**r) for r in data.pop("format_results", [])]

        # Remove unknown fields that may not be in the dataclass
        import dataclasses

        known_fields = {f.name for f in dataclasses.fields(cls)}
        data = {k: v for k, v in data.items() if k in known_fields}

        result = cls(**data)
        result.file_results = file_results
        result.function_results = function_results
        result.format_results = format_results
        return result


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark runs."""

    # Formats to test
    formats: List[str] = field(default_factory=lambda: ["yaml", "toon", "json"])

    # Limits
    max_files: Optional[int] = None
    max_functions: Optional[int] = None
    max_spec_tokens: int = 5000

    # Parallelization
    workers: int = 3

    # Output
    output_dir: str = "benchmark_output"
    save_generated: bool = True

    # Verbosity
    verbose: bool = False

    # Execution mode
    use_llm: bool = True

    # LLM settings
    max_tokens: int = 4000

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
