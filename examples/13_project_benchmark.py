#!/usr/bin/env python3
"""
Project Benchmark - Simplified.

Uses the standardized benchmark API for project-level benchmarking.

Usage:
    python examples/13_project_benchmark_simple.py --project tests/samples/
    python examples/13_project_benchmark_simple.py --project ~/myproject/ --formats yaml toon
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig


def print_project_results(result):
    """Print project benchmark results."""
    print(f"\n{'=' * 70}")
    print("PROJECT BENCHMARK RESULTS")
    print(f"{'=' * 70}")
    print(f"Project: {result.source_path}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Files: {result.total_files}")
    print(f"Avg Score: {result.avg_score:.1f}%")
    print(f"Syntax OK: {result.syntax_ok_rate:.0f}%")
    print(f"Time: {result.total_time:.1f}s")

    # Format comparison
    if result.format_scores:
        print(f"\n{'Format':<15} {'Score':>10}")
        print("-" * 30)
        for fmt, score in sorted(result.format_scores.items(), key=lambda x: -x[1]):
            print(f"{fmt:<15} {score:>8.1f}%")

    # Per-file results
    print("\n📁 Per-File Results:")
    print("-" * 70)
    print(f"{'File':<35} {'Score':>10} {'Syntax':>10}")
    print("-" * 70)

    for fr in sorted(result.file_results, key=lambda x: -x.score)[:10]:
        status = "✓" if fr.syntax_ok else "✗"
        print(f"{Path(fr.file_path).name[:34]:<35} {fr.score:>8.1f}% {status:>10}")

    if len(result.file_results) > 10:
        print(f"... and {len(result.file_results) - 10} more files")

    print(f"\n🏆 Best format: {result.best_format}")


def main():
    parser = argparse.ArgumentParser(description="Project Benchmark (Simplified)")
    parser.add_argument("--project", "-p", default="tests/samples/")
    parser.add_argument("--formats", nargs="+", default=["yaml", "toon", "json"])
    parser.add_argument("--limit", "-l", type=int, default=5)
    parser.add_argument(
        "--output", "-o", default="examples/output/project_benchmark.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template fallback)"
    )
    args = parser.parse_args()

    print(f"Running project benchmark on {args.project}")
    print(f"Formats: {', '.join(args.formats)}")

    config = BenchmarkConfig(
        formats=args.formats,
        max_files=args.limit,
        verbose=args.verbose,
        use_llm=not args.no_llm,
    )

    runner = BenchmarkRunner(config=config)
    result = runner.run_project_benchmark(
        args.project,
        formats=args.formats,
        limit=args.limit,
        verbose=args.verbose,
    )

    print_project_results(result)
    result.save(args.output)
    print(f"\n📄 Saved: {args.output}")


if __name__ == "__main__":
    main()
