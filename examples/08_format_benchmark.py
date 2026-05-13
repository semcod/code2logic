#!/usr/bin/env python3
"""
Format Benchmark - Simplified.

Uses the standardized benchmark API from code2logic.benchmarks.

Usage:
    python examples/08_format_benchmark_simple.py
    python examples/08_format_benchmark_simple.py --folder code2logic/ --formats yaml toon json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig


def print_format_comparison(result):
    """Print format comparison results."""
    print(f"\n{'=' * 70}")
    print("FORMAT BENCHMARK RESULTS")
    print(f"{'=' * 70}")
    print(f"Files: {result.total_files}")
    print(f"Time: {result.total_time:.1f}s")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")

    # Format comparison table
    print(f"\n{'Format':<12} {'Avg Score':>12} {'Syntax OK':>12} {'Runs OK':>12}")
    print("-" * 50)

    for fmt, score in sorted(result.format_scores.items(), key=lambda x: -x[1]):
        syntax_rates = [
            fr.format_results[fmt].syntax_ok
            for fr in result.file_results
            if fmt in fr.format_results
        ]
        runs_rates = [
            fr.format_results[fmt].runs_ok
            for fr in result.file_results
            if fmt in fr.format_results
        ]
        syntax_pct = sum(syntax_rates) / len(syntax_rates) * 100 if syntax_rates else 0
        runs_pct = sum(runs_rates) / len(runs_rates) * 100 if runs_rates else 0
        print(f"{fmt:<12} {score:>10.1f}% {syntax_pct:>10.0f}% {runs_pct:>10.0f}%")

    print(f"\n🏆 Best format: {result.best_format} ({result.best_score:.1f}%)")


def print_per_file_results(result):
    """Print per-file breakdown."""
    print("\n📁 Per-File Results:")
    print("-" * 70)

    formats = list(result.format_scores.keys())
    print(f"{'File':<30} ", end="")
    for fmt in formats:
        print(f"{fmt:>12}", end="")
    print()
    print("-" * 70)

    for fr in result.file_results:
        print(f"{Path(fr.file_path).name[:29]:<30} ", end="")
        for fmt in formats:
            if fmt in fr.format_results:
                score = fr.format_results[fmt].score
                print(f"{score:>10.1f}%", end="  ")
            else:
                print(f"{'N/A':>12}", end="")
        print()


def main():
    parser = argparse.ArgumentParser(description="Format Benchmark (Simplified)")
    parser.add_argument("--folder", "-f", default="tests/samples/")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["yaml", "toon", "json", "gherkin", "markdown", "logicml"],
    )
    parser.add_argument("--limit", "-l", type=int, default=5)
    parser.add_argument(
        "--output", "-o", default="examples/output/format_benchmark.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template fallback)"
    )
    args = parser.parse_args()

    print(f"Running format benchmark on {args.folder}")
    print(f"Formats: {', '.join(args.formats)}")

    # Use the standardized benchmark runner
    config = BenchmarkConfig(
        formats=args.formats,
        max_files=args.limit,
        verbose=args.verbose,
        use_llm=not args.no_llm,
    )

    runner = BenchmarkRunner(config=config)
    result = runner.run_format_benchmark(
        args.folder,
        formats=args.formats,
        limit=args.limit,
        verbose=args.verbose,
    )

    # Print results
    print_format_comparison(result)
    if args.verbose:
        print_per_file_results(result)

    # Save
    result.save(args.output)
    print(f"\n📄 Results saved: {args.output}")


if __name__ == "__main__":
    main()
