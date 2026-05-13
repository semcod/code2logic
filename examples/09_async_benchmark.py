#!/usr/bin/env python3
"""
Async Benchmark - Simplified.

Uses the standardized benchmark API with parallel processing.

Usage:
    python examples/09_async_benchmark_simple.py
    python examples/09_async_benchmark_simple.py --folder tests/samples/ --formats yaml toon
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig


def print_results(result):
    """Print benchmark results."""
    print(f"\n{'=' * 60}")
    print("ASYNC BENCHMARK RESULTS")
    print(f"{'=' * 60}")
    print(f"Files: {result.total_files}")
    print(f"Time: {result.total_time:.1f}s")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Avg Score: {result.avg_score:.1f}%")
    print(f"Syntax OK: {result.syntax_ok_rate:.0f}%")

    if result.format_scores:
        print(f"\n{'Format':<15} {'Score':>10}")
        print("-" * 30)
        for fmt, score in sorted(result.format_scores.items(), key=lambda x: -x[1]):
            print(f"{fmt:<15} {score:>8.1f}%")

    print(f"\n🏆 Best: {result.best_format} ({result.best_score:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Async Benchmark (Simplified)")
    parser.add_argument("--folder", "-f", default="tests/samples/")
    parser.add_argument("--formats", nargs="+", default=["yaml", "toon", "json"])
    parser.add_argument("--limit", "-l", type=int, default=3)
    parser.add_argument(
        "--output", "-o", default="examples/output/async_benchmark.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template fallback)"
    )
    args = parser.parse_args()

    print(f"Running async benchmark on {args.folder}")

    config = BenchmarkConfig(
        formats=args.formats,
        max_files=args.limit,
        workers=3,
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

    print_results(result)
    result.save(args.output)
    print(f"\n📄 Saved: {args.output}")


if __name__ == "__main__":
    main()
