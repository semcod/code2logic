"""
Reproduction Benchmark for Code2Logic.

Compares reproduction quality across different output formats:
- Gherkin (BDD specification)
- CSV (tabular)
- JSON (structured)
- YAML (human-readable)
- Markdown (documentation)

Usage:
    from code2logic.benchmark import ReproductionBenchmark

    benchmark = ReproductionBenchmark()
    results = benchmark.run_all("path/to/file.py")
"""

import json
import time

# Load .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analyzer import analyze_project
from .file_formats import generate_file_csv, generate_file_json, generate_file_yaml
from .generators import (
    CSVGenerator,
    JSONGenerator,
    MarkdownGenerator,
    YAMLGenerator,
)
from .gherkin import GherkinGenerator
from .llm_clients import BaseLLMClient, get_client
from .reproduction import compare_code, extract_code_block, generate_file_gherkin


@dataclass
class FormatResult:
    """Result for a single format test."""

    format_name: str
    spec_chars: int
    spec_tokens: int
    generated_chars: int
    similarity: float
    structural_score: float
    classes_match: bool
    functions_match: bool
    generation_time: float
    error: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark result."""

    source_file: str
    source_chars: int
    source_classes: int
    source_functions: int
    timestamp: str
    model: str
    formats: List[FormatResult]
    best_format: str
    best_similarity: float


# Prompts optimized for each format
FORMAT_PROMPTS = {
    "gherkin": """Generate Python code from this Gherkin/BDD specification.
The specification describes dataclasses, classes, and functions.
Generate ONLY the Python code, wrapped in ```python ... ``` blocks.

{spec}

Rules:
1. Use @dataclass decorator for dataclasses
2. Include all attributes with correct types
3. Include default values where specified
4. Add docstrings to all classes""",
    "csv": """Generate Python code from this CSV analysis.
Each row describes a code element (class, function, attribute).
Generate ONLY the Python code, wrapped in ```python ... ``` blocks.

{spec}

Rules:
1. Create classes for rows with type='class'
2. Add attributes based on rows with type='attribute'
3. Add methods based on rows with type='method'
4. Include proper type hints""",
    "json": """Generate Python code from this JSON structure analysis.
Generate ONLY the Python code, wrapped in ```python ... ``` blocks.

{spec}

Rules:
1. Create all classes listed in 'classes'
2. Add all attributes with their types
3. Add all methods with their signatures
4. Use dataclasses where appropriate""",
    "yaml": """Generate Python code from this YAML structure analysis.
Generate ONLY the Python code, wrapped in ```python ... ``` blocks.

{spec}

Rules:
1. Create all classes with their attributes
2. Use proper Python type hints
3. Add docstrings based on descriptions
4. Use dataclasses for data containers""",
    "markdown": """Generate Python code from this Markdown documentation.
Generate ONLY the Python code, wrapped in ```python ... ``` blocks.

{spec}

Rules:
1. Create all documented classes
2. Add all listed attributes and methods
3. Use proper type hints
4. Add docstrings""",
}


class ReproductionBenchmark:
    """Benchmark reproduction quality across formats."""

    def __init__(self, client: BaseLLMClient = None):
        """Initialize benchmark.

        Args:
            client: LLM client (default: auto-detect)
        """
        self.client = client or get_client()
        self.generators = {
            "gherkin": GherkinGenerator(),
            "csv": CSVGenerator(),
            "json": JSONGenerator(),
            "yaml": YAMLGenerator(),
            "markdown": MarkdownGenerator(),
        }

    def generate_spec(
        self, file_path: Path, format_name: str, detail: str = "full"
    ) -> str:
        """Generate specification in given format.

        Args:
            file_path: Source file path
            format_name: Format name (gherkin, csv, json, yaml, markdown)
            detail: Detail level

        Returns:
            Specification string
        """
        # Use file-specific generators for better reproduction
        if format_name == "gherkin":
            return generate_file_gherkin(file_path)
        elif format_name == "csv":
            return generate_file_csv(file_path)
        elif format_name == "json":
            return generate_file_json(file_path)
        elif format_name == "yaml":
            return generate_file_yaml(file_path)

        # For markdown, use project-level analysis
        project = analyze_project(str(file_path.parent))
        gen = self.generators[format_name]
        return gen.generate(project)

    def reproduce_with_format(
        self,
        file_path: Path,
        format_name: str,
        original_code: str,
    ) -> FormatResult:
        """Test reproduction with a specific format.

        Args:
            file_path: Source file path
            format_name: Format to test
            original_code: Original source code

        Returns:
            FormatResult with metrics
        """
        start_time = time.time()

        try:
            # Generate specification
            spec = self.generate_spec(file_path, format_name)
            spec_chars = len(spec)
            spec_tokens = spec_chars // 4

            # Truncate spec if too long
            max_spec = 8000
            if len(spec) > max_spec:
                spec = spec[:max_spec] + "\n... (truncated)"

            # Generate code from spec
            prompt = FORMAT_PROMPTS.get(format_name, FORMAT_PROMPTS["gherkin"])
            prompt = prompt.format(spec=spec)

            system = "You are an expert Python developer. Generate clean, production-ready code."

            response = self.client.generate(prompt, system=system, max_tokens=8000)
            generated = extract_code_block(response)

            # Compare
            comparison = compare_code(original_code, generated)

            # Check structural elements
            orig_classes = original_code.count("class ")
            gen_classes = generated.count("class ")
            orig_funcs = original_code.count("def ")
            gen_funcs = generated.count("def ")

            return FormatResult(
                format_name=format_name,
                spec_chars=spec_chars,
                spec_tokens=spec_tokens,
                generated_chars=len(generated),
                similarity=comparison["similarity_percent"],
                structural_score=comparison["structural_score"],
                classes_match=(orig_classes == gen_classes),
                functions_match=(orig_funcs == gen_funcs),
                generation_time=time.time() - start_time,
            )

        except Exception as e:
            return FormatResult(
                format_name=format_name,
                spec_chars=0,
                spec_tokens=0,
                generated_chars=0,
                similarity=0,
                structural_score=0,
                classes_match=False,
                functions_match=False,
                generation_time=time.time() - start_time,
                error=str(e),
            )

    def run_single(self, file_path: str, formats: List[str] = None) -> BenchmarkResult:
        """Run benchmark on a single file.

        Args:
            file_path: Path to source file
            formats: Formats to test (default: all)

        Returns:
            BenchmarkResult
        """
        path = Path(file_path)
        original_code = path.read_text()

        formats = formats or list(self.generators.keys())

        # Count source elements
        source_classes = original_code.count("class ")
        source_functions = original_code.count("def ")

        results = []
        for fmt in formats:
            print(f"  Testing {fmt}...", end=" ", flush=True)
            result = self.reproduce_with_format(path, fmt, original_code)
            results.append(result)

            if result.error:
                print(f"ERROR: {result.error[:50]}")
            else:
                print(f"{result.similarity:.1f}% similarity")

        # Find best format
        valid_results = [r for r in results if not r.error]
        if valid_results:
            best = max(valid_results, key=lambda r: r.similarity)
            best_format = best.format_name
            best_similarity = best.similarity
        else:
            best_format = "none"
            best_similarity = 0

        return BenchmarkResult(
            source_file=str(file_path),
            source_chars=len(original_code),
            source_classes=source_classes,
            source_functions=source_functions,
            timestamp=datetime.now().isoformat(),
            model=getattr(self.client, "model", "unknown"),
            formats=results,
            best_format=best_format,
            best_similarity=best_similarity,
        )

    def run_all(self, files: List[str], output_dir: str = None) -> Dict[str, Any]:
        """Run benchmark on multiple files.

        Args:
            files: List of file paths
            output_dir: Optional output directory for results

        Returns:
            Combined results
        """
        all_results = []

        print("=" * 60)
        print("REPRODUCTION BENCHMARK")
        print("=" * 60)

        for file_path in files:
            print(f"\nBenchmarking: {file_path}")
            result = self.run_single(file_path)
            all_results.append(result)

        # Generate summary
        summary = self._generate_summary(all_results)

        # Save if output_dir provided
        if output_dir:
            self._save_results(Path(output_dir), all_results, summary)

        return {
            "results": [asdict(r) for r in all_results],
            "summary": summary,
        }

    def _generate_summary(self, results: List[BenchmarkResult]) -> Dict[str, Any]:
        """Generate summary from benchmark results."""
        format_scores = {}

        for result in results:
            for fmt_result in result.formats:
                if fmt_result.format_name not in format_scores:
                    format_scores[fmt_result.format_name] = []
                if not fmt_result.error:
                    format_scores[fmt_result.format_name].append(fmt_result.similarity)

        avg_scores = {
            fmt: sum(scores) / len(scores) if scores else 0
            for fmt, scores in format_scores.items()
        }

        best_format = (
            max(avg_scores.items(), key=lambda x: x[1])[0] if avg_scores else "none"
        )

        return {
            "total_files": len(results),
            "average_by_format": avg_scores,
            "best_format": best_format,
            "best_average": avg_scores.get(best_format, 0),
        }

    def _save_results(
        self, output_dir: Path, results: List[BenchmarkResult], summary: Dict
    ):
        """Save benchmark results."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON results
        data = {
            "results": [asdict(r) for r in results],
            "summary": summary,
        }
        (output_dir / "benchmark_results.json").write_text(json.dumps(data, indent=2))

        # Generate markdown report
        report = self._generate_report(results, summary)
        (output_dir / "BENCHMARK_REPORT.md").write_text(report)

        print(f"\nResults saved to: {output_dir}")

    def _generate_report(self, results: List[BenchmarkResult], summary: Dict) -> str:
        """Generate markdown benchmark report."""
        lines = [
            "# Reproduction Benchmark Report",
            "",
            f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            "",
            f"- **Files tested:** {summary['total_files']}",
            f"- **Best format:** {summary['best_format']} ({summary['best_average']:.1f}% avg)",
            "",
            "### Average Similarity by Format",
            "",
            "| Format | Avg Similarity |",
            "|--------|----------------|",
        ]

        for fmt, score in sorted(
            summary["average_by_format"].items(), key=lambda x: -x[1]
        ):
            lines.append(f"| {fmt} | {score:.1f}% |")

        lines.extend(["", "## Detailed Results", ""])

        for result in results:
            lines.append(f"### {result.source_file}")
            lines.append("")
            lines.append(f"- **Classes:** {result.source_classes}")
            lines.append(f"- **Functions:** {result.source_functions}")
            lines.append(
                f"- **Best:** {result.best_format} ({result.best_similarity:.1f}%)"
            )
            lines.append("")
            lines.append("| Format | Similarity | Structural | Classes | Functions |")
            lines.append("|--------|------------|------------|---------|-----------|")

            for fmt in result.formats:
                if fmt.error:
                    lines.append(f"| {fmt.format_name} | ERROR | - | - | - |")
                else:
                    cls_ok = "✓" if fmt.classes_match else "✗"
                    func_ok = "✓" if fmt.functions_match else "✗"
                    lines.append(
                        f"| {fmt.format_name} | {fmt.similarity:.1f}% | "
                        f"{fmt.structural_score:.1f}% | {cls_ok} | {func_ok} |"
                    )

            lines.append("")

        return "\n".join(lines)


def run_benchmark(
    files: List[str],
    output_dir: str = "benchmark_results",
    provider: str = None,
    model: str = None,
) -> Dict[str, Any]:
    """Run reproduction benchmark.

    Args:
        files: List of source files to test
        output_dir: Output directory for results
        provider: LLM provider (default: auto)
        model: Model to use

    Returns:
        Benchmark results
    """
    client = get_client(provider, model)
    benchmark = ReproductionBenchmark(client)
    return benchmark.run_all(files, output_dir)
