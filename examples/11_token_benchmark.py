#!/usr/bin/env python3
"""
Token-Aware Benchmark - Simplified.

Uses the standardized benchmark API with token efficiency tracking.

Usage:
    python examples/11_token_benchmark_simple.py
    python examples/11_token_benchmark_simple.py --folder tests/samples/ --formats yaml toon
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig


def print_token_efficiency(result):
    """Print token efficiency analysis."""
    print(f"\n{'=' * 70}")
    print("TOKEN EFFICIENCY ANALYSIS")
    print(f"{'=' * 70}")
    print(f"Files: {result.total_files}")
    print(f"Total Time: {result.total_time:.1f}s")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")

    # Calculate token efficiency per format
    print(f"\n{'Format':<12} {'Score':>10} {'Avg Tokens':>12} {'Efficiency':>12}")
    print("-" * 50)

    for fmt in sorted(result.format_scores.keys()):
        # Get all format results
        tokens_list = []
        scores_list = []
        for fr in result.file_results:
            if fmt in fr.format_results:
                fmt_r = fr.format_results[fmt]
                if fmt_r.spec_tokens > 0:
                    tokens_list.append(fmt_r.spec_tokens)
                    scores_list.append(fmt_r.score)

        if tokens_list:
            avg_tokens = sum(tokens_list) / len(tokens_list)
            avg_score = sum(scores_list) / len(scores_list)
            efficiency = avg_score / avg_tokens * 100 if avg_tokens > 0 else 0
            print(
                f"{fmt:<12} {avg_score:>8.1f}% {avg_tokens:>10.0f} {efficiency:>10.2f}"
            )

    print(f"\n🏆 Best format: {result.best_format}")


def main():
    parser = argparse.ArgumentParser(description="Token Benchmark (Simplified)")
    parser.add_argument("--folder", "-f", default="tests/samples/")
    parser.add_argument(
        "--formats", nargs="+", default=["yaml", "toon", "json", "logicml"]
    )
    parser.add_argument("--limit", "-l", type=int, default=4)
    parser.add_argument(
        "--output", "-o", default="examples/output/token_benchmark.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template fallback)"
    )
    args = parser.parse_args()

    print(f"Running token benchmark on {args.folder}")
    print(f"Formats: {', '.join(args.formats)}")

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

    print_token_efficiency(result)
    result.save(args.output)
    print(f"\n📄 Saved: {args.output}")


if __name__ == "__main__":
    main()
