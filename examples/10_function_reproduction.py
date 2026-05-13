#!/usr/bin/env python3
"""
Function-Level Reproduction - Simplified.

Uses the standardized benchmark API for function-level testing.

Usage:
    python examples/10_function_reproduction_simple.py
    python examples/10_function_reproduction_simple.py --file tests/samples/sample_functions.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig


def print_results(result):
    """Print function reproduction results."""
    print(f"\n{'=' * 60}")
    print("FUNCTION REPRODUCTION RESULTS")
    print(f"{'=' * 60}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Functions: {result.total_functions}")
    print(f"Avg Similarity: {result.avg_similarity:.1f}%")
    print(f"Time: {result.total_time:.1f}s")

    print(f"\n{'Function':<30} {'Similarity':>12} {'Syntax':>8}")
    print("-" * 55)

    for fr in result.function_results:
        status = "✓" if fr.syntax_ok else "✗"
        print(f"{fr.function_name[:29]:<30} {fr.similarity:>10.1f}% {status:>8}")

    # Summary
    syntax_ok = sum(1 for fr in result.function_results if fr.syntax_ok)
    print(f"\nSyntax OK: {syntax_ok}/{result.total_functions}")


def main():
    parser = argparse.ArgumentParser(description="Function Reproduction (Simplified)")
    parser.add_argument("--file", "-f", default="tests/samples/sample_functions.py")
    parser.add_argument("--limit", "-l", type=int, default=5)
    parser.add_argument(
        "--output", "-o", default="examples/output/function_reproduction.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (skeleton fallback)"
    )
    args = parser.parse_args()

    print(f"Testing function reproduction: {args.file}")

    runner = BenchmarkRunner(config=BenchmarkConfig(use_llm=not args.no_llm))
    result = runner.run_function_benchmark(
        args.file,
        limit=args.limit,
        verbose=args.verbose,
    )

    print_results(result)
    result.save(args.output)
    print(f"\n📄 Saved: {args.output}")


if __name__ == "__main__":
    main()
