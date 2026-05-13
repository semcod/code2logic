#!/usr/bin/env python3
"""
Repeatability Test for Code Generation.

Tests how repeatable/consistent code generation is across multiple invocations.
Compares YAML, LogicML, and Gherkin formats for consistency.

Usage:
    python examples/14_repeatability_test.py --file tests/samples/sample_class.py
    python examples/14_repeatability_test.py --file tests/samples/sample_class.py --runs 5
"""

import argparse
import difflib
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic import analyze_project, get_client
from code2logic.gherkin import GherkinGenerator
from code2logic.generators import YAMLGenerator, JSONGenerator
from code2logic.logicml import LogicMLGenerator
from code2logic.toon_format import TOONGenerator
from code2logic.markdown_format import MarkdownHybridGenerator
from code2logic.reproduction import extract_code_block
from code2logic.models import ProjectInfo


def _template_generate(spec: str, fmt: str, file_name: str) -> str:
    """Generate minimal Python code without an LLM (baseline mode)."""
    import re

    classes = re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", spec)
    functions = re.findall(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", spec)
    functions += re.findall(r"\bScenario:\s*([A-Za-z_][A-Za-z0-9_]*)", spec)

    def uniq(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for it in items:
            if it and it not in seen:
                seen.add(it)
                out.append(it)
        return out

    classes = [c for c in uniq(classes) if c.isidentifier()][:3]
    functions = [f for f in uniq(functions) if f.isidentifier() and f not in classes][
        :5
    ]

    code = """from __future__ import annotations

from dataclasses import dataclass
from typing import Any

"""

    if not classes and not functions:
        classes = ["GeneratedClass"]
        functions = ["generated_function"]

    for cls in classes:
        code += f"""@dataclass
class {cls}:
    \"\"\"Generated placeholder for {file_name} ({fmt}).\"\"\"
    value: Any = None

"""

    for fn in functions:
        code += f"""def {fn}(*args: Any, **kwargs: Any) -> Any:
    \"\"\"Generated placeholder for {file_name} ({fmt}).\"\"\"
    return None

"""

    return code


@dataclass
class RunResult:
    """Result of a single generation run."""

    run_id: int
    format: str
    code: str
    lines: int
    syntax_ok: bool
    time_s: float


@dataclass
class RepeatabilityResult:
    """Repeatability analysis for a format."""

    format: str
    runs: List[RunResult]

    # Similarity metrics
    avg_similarity: float = 0.0
    min_similarity: float = 0.0
    max_similarity: float = 0.0

    # Consistency
    all_syntax_ok: bool = False
    line_variance: float = 0.0

    # Differences
    diff_lines: List[str] = field(default_factory=list)


def generate_spec(project: ProjectInfo, fmt: str) -> str:
    """Generate specification in given format."""
    if fmt == "gherkin":
        gen = GherkinGenerator()
        return gen.generate(project)
    elif fmt == "yaml":
        gen = YAMLGenerator()
        return gen.generate(project, detail="full")
    elif fmt == "json":
        gen = JSONGenerator()
        return gen.generate(project, detail="full")
    elif fmt == "markdown":
        gen = MarkdownHybridGenerator()
        spec = gen.generate(project)
        return spec.content
    elif fmt == "logicml":
        gen = LogicMLGenerator()
        spec = gen.generate(project)
        return spec.content
    elif fmt == "toon":
        gen = TOONGenerator()
        return gen.generate(project, detail="full")
    return ""


def get_reproduction_prompt(spec: str, fmt: str, file_name: str) -> str:
    """Generate reproduction prompt."""
    format_hints = {
        "json": "Parse the JSON structure and implement all classes and functions.",
        "yaml": "Parse the YAML structure and implement all classes and functions with exact signatures.",
        "gherkin": "Implement scenarios as SIMPLE, MINIMAL Python code. NO extra error classes.",
        "markdown": "Parse embedded Gherkin (behaviors) and YAML (structures).",
        "logicml": "Parse the LogicML spec precisely. 'sig' = exact signature, 'does' = docstring.",
        "toon": "Parse TOON tabular format. 'modules[N]{fields}:' = array of N items with fields. Match signatures exactly.",
    }

    return f"""Generate Python code from this {fmt.upper()} specification.
{format_hints.get(fmt, "")}

{spec[:4000]}

Requirements:
- Complete, working Python code for {file_name}
- Include imports and type hints
- Implement all functions with actual logic

```python
"""


def calculate_similarity(code1: str, code2: str) -> float:
    """Calculate similarity between two code strings."""
    if not code1 or not code2:
        return 0.0

    # Use difflib for similarity
    matcher = difflib.SequenceMatcher(None, code1, code2)
    return matcher.ratio() * 100


def get_diff(
    code1: str, code2: str, label1: str = "Run 1", label2: str = "Run 2"
) -> List[str]:
    """Get unified diff between two code versions."""
    lines1 = code1.splitlines(keepends=True)
    lines2 = code2.splitlines(keepends=True)

    diff = list(difflib.unified_diff(lines1, lines2, fromfile=label1, tofile=label2))
    return diff


def test_syntax(code: str) -> bool:
    """Test if code has valid Python syntax."""
    try:
        compile(code, "<string>", "exec")
        return True
    except:
        return False


def run_repeatability_test(
    file_path: str,
    formats: List[str],
    num_runs: int = 3,
    verbose: bool = False,
    no_llm: bool = False,
) -> Dict[str, RepeatabilityResult]:
    """Run repeatability test for given file and formats."""

    print(f"\n{'=' * 70}")
    print("REPEATABILITY TEST")
    print(f"{'=' * 70}")
    print(f"File: {file_path}")
    print(f"Formats: {', '.join(formats)}")
    print(f"Runs per format: {num_runs}")

    # Initialize LLM
    client = None
    if no_llm:
        print("Selected: none (template mode)")
        print("Model: none")
    else:
        try:
            client = get_client()
            provider_name = (
                getattr(client, "provider", None) or client.__class__.__name__
            )
            print(f"Selected: {provider_name}")
            print(f"Model: {getattr(client, 'model', 'default')}")
        except Exception as e:
            print(f"LLM not available: {e}")
            return {}

    # Analyze file
    print("\n📊 Analyzing file...")
    project = analyze_project(str(Path(file_path).parent), use_treesitter=False)

    # Find the specific module
    target_name = Path(file_path).name
    module = None
    for m in project.modules:
        if Path(m.path).name == target_name:
            module = m
            break

    if not module:
        print(f"Module not found: {target_name}")
        return {}

    # Create single-file project
    single_project = ProjectInfo(
        name=target_name,
        root_path=str(Path(file_path).parent),
        languages={"python": 1},
        modules=[module],
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=1,
        total_lines=module.lines_total,
        generated_at=datetime.now().isoformat(),
    )

    results = {}

    for fmt in formats:
        print(f"\n{'─' * 70}")
        print(f"FORMAT: {fmt.upper()}")
        print(f"{'─' * 70}")

        # Generate spec once
        spec = generate_spec(single_project, fmt)
        prompt = get_reproduction_prompt(spec, fmt, target_name)

        runs = []

        for run_id in range(1, num_runs + 1):
            print(f"  Run {run_id}/{num_runs}...", end=" ", flush=True)

            start = time.time()
            if client is None:
                code = _template_generate(spec, fmt, target_name)
            else:
                try:
                    response = client.generate(prompt, max_tokens=4000)
                    code = extract_code_block(response)
                except Exception as e:
                    code = ""
                    print(f"Error: {e}")

            elapsed = time.time() - start
            syntax_ok = test_syntax(code)

            run = RunResult(
                run_id=run_id,
                format=fmt,
                code=code,
                lines=len(code.split("\n")),
                syntax_ok=syntax_ok,
                time_s=elapsed,
            )
            runs.append(run)

            status = "✓" if syntax_ok else "✗"
            print(f"{run.lines} lines, {status} syntax, {elapsed:.1f}s")

        # Analyze repeatability
        result = RepeatabilityResult(format=fmt, runs=runs)

        # Calculate pairwise similarities
        similarities = []
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                sim = calculate_similarity(runs[i].code, runs[j].code)
                similarities.append(sim)

        if similarities:
            result.avg_similarity = sum(similarities) / len(similarities)
            result.min_similarity = min(similarities)
            result.max_similarity = max(similarities)

        # Check consistency
        result.all_syntax_ok = all(r.syntax_ok for r in runs)

        # Line variance
        line_counts = [r.lines for r in runs]
        if line_counts:
            avg_lines = sum(line_counts) / len(line_counts)
            result.line_variance = sum((l - avg_lines) ** 2 for l in line_counts) / len(
                line_counts
            )

        # Get diff between first and last run
        if len(runs) >= 2:
            result.diff_lines = get_diff(
                runs[0].code, runs[-1].code, "Run 1", f"Run {num_runs}"
            )

        results[fmt] = result

    return results


def print_repeatability_summary(results: Dict[str, RepeatabilityResult]):
    """Print repeatability summary."""

    print(f"\n{'=' * 70}")
    print("REPEATABILITY SUMMARY")
    print(f"{'=' * 70}")

    formats = list(results.keys())

    print("\n📊 Consistency Metrics:")
    print(f"{'─' * 70}")
    print(
        f"{'Format':<12} {'Avg Sim':>10} {'Min Sim':>10} {'Max Sim':>10} {'Syntax':>10} {'Line Var':>10}"
    )
    print(f"{'─' * 70}")

    for fmt in formats:
        r = results[fmt]
        syntax = (
            "100%"
            if r.all_syntax_ok
            else f"{sum(1 for run in r.runs if run.syntax_ok)}/{len(r.runs)}"
        )
        print(
            f"{fmt:<12} {r.avg_similarity:>9.1f}% {r.min_similarity:>9.1f}% {r.max_similarity:>9.1f}% {syntax:>10} {r.line_variance:>10.1f}"
        )

    print(f"{'─' * 70}")

    # Find best format
    best_consistency = max(formats, key=lambda f: results[f].avg_similarity)
    best_syntax = max(
        formats, key=lambda f: sum(1 for r in results[f].runs if r.syntax_ok)
    )
    lowest_variance = min(formats, key=lambda f: results[f].line_variance)

    print("\n🏆 Best Format:")
    print(
        f"   Most Consistent: {best_consistency} ({results[best_consistency].avg_similarity:.1f}%)"
    )
    print(f"   Best Syntax: {best_syntax}")
    print(
        f"   Lowest Variance: {lowest_variance} ({results[lowest_variance].line_variance:.1f})"
    )

    # Show diffs
    print("\n📝 Code Differences (Run 1 vs Last Run):")
    for fmt in formats:
        r = results[fmt]
        diff_count = len(
            [l for l in r.diff_lines if l.startswith("+") or l.startswith("-")]
        )
        print(f"\n   {fmt.upper()}: {diff_count} changed lines")

        # Show first few diff lines
        shown = 0
        for line in r.diff_lines:
            if line.startswith("+") or line.startswith("-"):
                if shown < 5:
                    print(f"      {line.rstrip()[:60]}")
                    shown += 1
        if diff_count > 5:
            print(f"      ... and {diff_count - 5} more changes")


def save_repeatability_report(results: Dict[str, RepeatabilityResult], output: str):
    """Save repeatability report to JSON."""
    data = {"timestamp": datetime.now().isoformat(), "formats": {}}

    for fmt, result in results.items():
        data["formats"][fmt] = {
            "avg_similarity": result.avg_similarity,
            "min_similarity": result.min_similarity,
            "max_similarity": result.max_similarity,
            "all_syntax_ok": result.all_syntax_ok,
            "line_variance": result.line_variance,
            "runs": [
                {
                    "run_id": r.run_id,
                    "lines": r.lines,
                    "syntax_ok": r.syntax_ok,
                    "time_s": r.time_s,
                }
                for r in result.runs
            ],
            "diff_line_count": len(
                [l for l in result.diff_lines if l.startswith("+") or l.startswith("-")]
            ),
        }

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n📄 Report saved: {output}")


def main():
    parser = argparse.ArgumentParser(description="Repeatability Test")
    parser.add_argument("--file", "-f", required=True, help="File to test")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["json", "yaml", "toon", "gherkin", "markdown", "logicml"],
    )
    parser.add_argument(
        "--runs", "-r", type=int, default=3, help="Number of runs per format"
    )
    parser.add_argument(
        "--output", "-o", default="examples/output/repeatability_test.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template baseline)"
    )
    args = parser.parse_args()

    results = run_repeatability_test(
        args.file,
        formats=args.formats,
        num_runs=args.runs,
        verbose=args.verbose,
        no_llm=args.no_llm,
    )

    if results:
        print_repeatability_summary(results)
        save_repeatability_report(results, args.output)


if __name__ == "__main__":
    main()
