#!/usr/bin/env python3
"""
Unified Benchmark Example.

Demonstrates the standardized benchmark API that consolidates
functionality from examples 10-13 into a simple, reusable interface.

Usage:
    python examples/15_unified_benchmark.py
    python examples/15_unified_benchmark.py --type format --folder tests/samples/
    python examples/15_unified_benchmark.py --type function --file tests/samples/sample_functions.py
    python examples/15_unified_benchmark.py --type project --folder tests/samples/ --limit 3
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from code2logic.benchmarks import (
    BenchmarkRunner,
    BenchmarkConfig,
)

from code2logic.llm_clients import get_client


def print_format_results(result):
    """Print format comparison results."""
    print(f"\n{'=' * 60}")
    print("FORMAT COMPARISON RESULTS")
    print(f"{'=' * 60}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Files: {result.total_files}")
    print(f"Time: {result.total_time:.1f}s")

    print(f"\n{'Format':<12} {'Avg Score':>12} {'Syntax OK':>12}")
    print("-" * 40)

    for fmt, score in sorted(result.format_scores.items(), key=lambda x: -x[1]):
        syntax_rates = [
            fr.format_results[fmt].syntax_ok
            for fr in result.file_results
            if fmt in fr.format_results
        ]
        syntax_pct = sum(syntax_rates) / len(syntax_rates) * 100 if syntax_rates else 0
        print(f"{fmt:<12} {score:>10.1f}% {syntax_pct:>10.0f}%")

    print(f"\n🏆 Best: {result.best_format} ({result.best_score:.1f}%)")


def print_function_results(result):
    """Print function reproduction results."""
    print(f"\n{'=' * 60}")
    print("FUNCTION REPRODUCTION RESULTS")
    print(f"{'=' * 60}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Functions: {result.total_functions}")
    print(f"Avg Similarity: {result.avg_similarity:.1f}%")

    print(f"\n{'Function':<25} {'Similarity':>12} {'Syntax':>8}")
    print("-" * 50)

    for fr in result.function_results:
        status = "✓" if fr.syntax_ok else "✗"
        print(f"{fr.function_name:<25} {fr.similarity:>10.1f}% {status:>8}")


def print_project_results(result):
    """Print project benchmark results."""
    print(f"\n{'=' * 60}")
    print("PROJECT BENCHMARK RESULTS")
    print(f"{'=' * 60}")
    print(f"Provider: {result.provider}")
    print(f"Model: {result.model}")
    print(f"Files: {result.total_files}")
    print(f"Avg Score: {result.avg_score:.1f}%")
    print(f"Time: {result.total_time:.1f}s")

    if result.format_scores:
        print(f"\n{'Format':<12} {'Score':>10}")
        print("-" * 25)
        for fmt, score in sorted(result.format_scores.items(), key=lambda x: -x[1]):
            print(f"{fmt:<12} {score:>8.1f}%")
        print(f"\n🏆 Best: {result.best_format}")


def main():
    parser = argparse.ArgumentParser(description="Unified Benchmark Example")
    parser.add_argument(
        "--type",
        "-t",
        choices=["format", "file", "function", "project"],
        default="format",
        help="Benchmark type",
    )
    parser.add_argument("--folder", "-f", default="tests/samples/")
    parser.add_argument("--file", help="Specific file for file/function benchmarks")
    parser.add_argument("--formats", nargs="+", default=["yaml", "toon", "json"])
    parser.add_argument("--limit", "-l", type=int, default=3)
    parser.add_argument(
        "--output", "-o", default="examples/output/unified_benchmark.json"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--no-llm", action="store_true", help="Run without LLM (template fallback)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Max parallel workers for LLM calls (default: 3)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4000,
        help="LLM max_tokens for code generation (default: 4000)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Force LLM provider (e.g. openrouter, litellm, ollama, groq, together)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Force LLM model string (e.g. anthropic/claude-3.5-sonnet)",
    )
    args = parser.parse_args()

    # Configure
    config = BenchmarkConfig(
        formats=args.formats,
        max_files=args.limit,
        verbose=args.verbose,
        use_llm=not args.no_llm,
        workers=args.workers,
        max_tokens=args.max_tokens,
    )

    client = None
    if not args.no_llm:
        # Allow explicit provider/model selection (e.g. Claude via OpenRouter).
        # lolm also supports env var LLM_PROVIDER; keep it in sync for transparency.
        if args.provider:
            os.environ["LLM_PROVIDER"] = args.provider
        client = get_client(provider=args.provider, model=args.model)

    runner = BenchmarkRunner(client=client, config=config)

    print(f"Running {args.type} benchmark...")
    print(f"Formats: {', '.join(args.formats)}")

    # Run appropriate benchmark
    if args.type == "format":
        result = runner.run_format_benchmark(
            args.folder, formats=args.formats, limit=args.limit, verbose=args.verbose
        )
        print_format_results(result)

    elif args.type == "file":
        file_path = args.file or "tests/samples/sample_functions.py"
        result = runner.run_file_benchmark(
            file_path, formats=args.formats, verbose=args.verbose
        )
        print_format_results(result)

    elif args.type == "function":
        file_path = args.file or "tests/samples/sample_functions.py"
        result = runner.run_function_benchmark(
            file_path, limit=args.limit, verbose=args.verbose
        )
        print_function_results(result)

    elif args.type == "project":
        result = runner.run_project_benchmark(
            args.folder, formats=args.formats, limit=args.limit, verbose=args.verbose
        )
        print_project_results(result)

    # Save results
    result.save(args.output)
    print(f"\n📄 Results saved: {args.output}")


if __name__ == "__main__":
    main()
