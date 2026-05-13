#!/usr/bin/env python3
"""
Comprehensive Analysis - Simplified.

Uses the standardized benchmark API for comprehensive format analysis.

Usage:
    python examples/12_comprehensive_analysis_simple.py
    python examples/12_comprehensive_analysis_simple.py --folder tests/samples/
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig

ALL_FORMATS = ["yaml", "json", "logicml", "gherkin", "markdown", "toon"]


def print_comprehensive_analysis(result):
    """Print comprehensive format analysis."""
    print(f"\n{'=' * 70}")
    print("COMPREHENSIVE FORMAT ANALYSIS")
    print(f"{'=' * 70}")
    print(f"Files: {result.total_files}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Formats tested: {len(result.format_scores)}")
    print(f"Total time: {result.total_time:.1f}s")

    # Format comparison
    print("\n📊 Format Comparison:")
    print("-" * 70)
    print(
        f"{'Format':<12} {'Score':>10} {'Syntax%':>10} {'Runs%':>10} {'Efficiency':>12}"
    )
    print("-" * 70)

    for fmt in sorted(
        result.format_scores.keys(), key=lambda f: -result.format_scores[f]
    ):
        score = result.format_scores[fmt]

        # Calculate syntax/runs rates
        syntax_ok = 0
        runs_ok = 0
        total = 0
        efficiency_sum = 0

        for fr in result.file_results:
            if fmt in fr.format_results:
                total += 1
                fmt_r = fr.format_results[fmt]
                if fmt_r.syntax_ok:
                    syntax_ok += 1
                if fmt_r.runs_ok:
                    runs_ok += 1
                if fmt_r.token_efficiency > 0:
                    efficiency_sum += fmt_r.token_efficiency

        syntax_pct = syntax_ok / total * 100 if total > 0 else 0
        runs_pct = runs_ok / total * 100 if total > 0 else 0
        avg_eff = efficiency_sum / total if total > 0 else 0

        print(
            f"{fmt:<12} {score:>8.1f}% {syntax_pct:>8.0f}% {runs_pct:>8.0f}% {avg_eff:>10.2f}"
        )

    # Conclusions
    print("\n💡 Conclusions:")
    print("-" * 70)

    if result.format_scores:
        best_score = max(result.format_scores.items(), key=lambda x: x[1])
        print(f"   Best overall score: {best_score[0]} ({best_score[1]:.1f}%)")

        # Find most compact
        sizes = {}
        for fr in result.file_results:
            for fmt, fmt_r in fr.format_results.items():
                if fmt not in sizes:
                    sizes[fmt] = []
                sizes[fmt].append(fmt_r.spec_size)

        if sizes:
            avg_sizes = {fmt: sum(s) / len(s) for fmt, s in sizes.items() if s}
            if avg_sizes:
                most_compact = min(avg_sizes.items(), key=lambda x: x[1])
                print(
                    f"   Most compact format: {most_compact[0]} ({most_compact[1]:.0f} chars avg)"
                )

    print(f"\n🏆 Recommended: {result.best_format}")


def main():
    parser = argparse.ArgumentParser(description="Comprehensive Analysis (Simplified)")
    parser.add_argument("--folder", "-f", default="tests/samples/")
    parser.add_argument("--formats", nargs="+", default=ALL_FORMATS)
    parser.add_argument("--limit", "-l", type=int, default=4)
    parser.add_argument(
        "--output", "-o", default="examples/output/comprehensive_analysis.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template fallback)"
    )
    args = parser.parse_args()

    print(f"Running comprehensive analysis on {args.folder}")
    print(f"Testing {len(args.formats)} formats...")

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

    print_comprehensive_analysis(result)
    result.save(args.output)
    print(f"\n📄 Saved: {args.output}")


if __name__ == "__main__":
    main()
