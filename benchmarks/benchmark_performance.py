#!/usr/bin/env python3
"""
Performance benchmark comparing original vs optimized analyzer.

Run with: python benchmarks/benchmark_performance.py
"""

import time
import tempfile
import shutil
from pathlib import Path
import statistics

# Add parent to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from code2flow import ProjectAnalyzer, FAST_CONFIG
from code2flow.core.streaming_analyzer import (
    StreamingAnalyzer,
    STRATEGY_QUICK,
    STRATEGY_STANDARD,
    STRATEGY_DEEP,
)


def create_test_project(size: str = "medium") -> str:
    """Create test project of specified size."""
    tmp_dir = Path(tempfile.mkdtemp())

    configs = {
        "small": {"modules": 10, "funcs_per_module": 5},
        "medium": {"modules": 50, "funcs_per_module": 10},
        "large": {"modules": 100, "funcs_per_module": 20},
    }

    config = configs.get(size, configs["medium"])

    for i in range(config["modules"]):
        lines = []

        # Add class
        lines.append(f"class Module{i}:")
        lines.append(f'    """Module {i} documentation."""')
        lines.append("")
        lines.append("    def __init__(self):")
        lines.append(f"        self.value = {i}")
        lines.append("")

        # Add methods
        for j in range(config["funcs_per_module"] // 2):
            lines.append(f"    def method_{j}(self, x):")
            lines.append("        if x > 0:")
            lines.append("            return self.value + x")
            lines.append("        return None")
            lines.append("")

        # Add standalone functions
        for j in range(config["funcs_per_module"] // 2):
            lines.append(f"def standalone_{i}_{j}(data):")
            lines.append("    result = []")
            lines.append("    for item in data:")
            lines.append("        if item > 0:")
            lines.append("            result.append(item * 2)")
            lines.append("    return result")
            lines.append("")

        # Add main for first module
        if i == 0:
            lines.append('if __name__ == "__main__":')
            lines.append('    print("Main entry point")')

        (tmp_dir / f"module_{i}.py").write_text("\n".join(lines))

    return str(tmp_dir)


def benchmark_original_analyzer(project_path: str, runs: int = 3) -> dict:
    """Benchmark original ProjectAnalyzer."""
    print(f"\n[Original Analyzer - {runs} runs]")

    times = []

    for run in range(runs):
        start = time.time()

        FAST_CONFIG.performance.parallel_enabled = False
        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(project_path)

        elapsed = time.time() - start
        times.append(elapsed)

        print(
            f"  Run {run + 1}: {elapsed:.2f}s - {result.get_function_count()} functions"
        )

    return {
        "avg_time": statistics.mean(times),
        "min_time": min(times),
        "max_time": max(times),
        "functions": result.get_function_count() if "result" in dir() else 0,
    }


def benchmark_streaming_analyzer(project_path: str, runs: int = 3) -> dict:
    """Benchmark new StreamingAnalyzer."""
    print(f"\n[Streaming Analyzer (Quick) - {runs} runs]")

    times = []

    for run in range(runs):
        start = time.time()

        analyzer = StreamingAnalyzer(strategy=STRATEGY_QUICK)

        function_count = 0
        for update in analyzer.analyze_streaming(project_path):
            if update["type"] == "file_complete":
                function_count += update.get("functions", 0)
            elif update["type"] == "complete":
                pass

        elapsed = time.time() - start
        times.append(elapsed)

        print(f"  Run {run + 1}: {elapsed:.2f}s")

    return {
        "avg_time": statistics.mean(times),
        "min_time": min(times),
        "max_time": max(times),
        "functions": function_count,
    }


def benchmark_with_strategies(project_path: str) -> dict:
    """Benchmark all strategies."""
    strategies = {
        "Quick": STRATEGY_QUICK,
        "Standard": STRATEGY_STANDARD,
        "Deep": STRATEGY_DEEP,
    }

    results = {}

    for name, strategy in strategies.items():
        print(f"\n[Strategy: {name}]")

        start = time.time()

        analyzer = StreamingAnalyzer(strategy=strategy)
        stats = {"files": 0, "functions": 0, "nodes": 0}

        for update in analyzer.analyze_streaming(project_path):
            if update["type"] == "file_complete":
                stats["files"] += 1
                stats["functions"] += update.get("functions", 0)
            elif update["type"] == "deep_complete":
                stats["nodes"] += update.get("nodes", 0)
            elif update["type"] == "complete":
                pass

        elapsed = time.time() - start

        print(f"  Time: {elapsed:.2f}s")
        print(f"  Files: {stats['files']}, Functions: {stats['functions']}")

        results[name] = {"time": elapsed, **stats}

    return results


def print_comparison(original: dict, streaming: dict):
    """Print comparison table."""
    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON")
    print("=" * 60)

    print(f"\n{'Metric':<20} {'Original':<15} {'Streaming':<15} {'Speedup':<10}")
    print("-" * 60)

    orig_avg = original["avg_time"]
    stream_avg = streaming["avg_time"]
    speedup = orig_avg / stream_avg if stream_avg > 0 else 0

    print(
        f"{'Avg Time':<20} {orig_avg:.2f}s{'':<9} {stream_avg:.2f}s{'':<9} {speedup:.1f}x"
    )
    print(
        f"{'Min Time':<20} {original['min_time']:.2f}s{'':<9} {streaming['min_time']:.2f}s{'':<9}"
    )
    print(
        f"{'Max Time':<20} {original['max_time']:.2f}s{'':<9} {streaming['max_time']:.2f}s{'':<9}"
    )

    print(
        f"\n{'Functions Found':<20} {original['functions']:<15} {streaming['functions']:<15}"
    )

    print("\n" + "=" * 60)


def main():
    """Run benchmark suite."""
    print("=" * 60)
    print("Code2Flow Performance Benchmark")
    print("=" * 60)

    # Create test project
    print("\n[Creating test project...]")
    project_path = create_test_project("medium")
    print(f"  Project created at: {project_path}")

    try:
        # Run benchmarks
        print("\n" + "=" * 60)
        print("BENCHMARK 1: Original vs Streaming")
        print("=" * 60)

        original_results = benchmark_original_analyzer(project_path, runs=3)
        streaming_results = benchmark_streaming_analyzer(project_path, runs=3)

        print_comparison(original_results, streaming_results)

        # Strategy comparison
        print("\n" + "=" * 60)
        print("BENCHMARK 2: Strategy Comparison")
        print("=" * 60)

        strategy_results = benchmark_with_strategies(project_path)

        print("\n[Summary]")
        print(f"  Quick strategy: {strategy_results['Quick']['time']:.2f}s")
        print(f"  Standard strategy: {strategy_results['Standard']['time']:.2f}s")
        print(f"  Deep strategy: {strategy_results['Deep']['time']:.2f}s")

        # Memory estimate
        print("\n" + "=" * 60)
        print("MEMORY ESTIMATES")
        print("=" * 60)
        print("  Original: ~500-2000MB (depends on CFG complexity)")
        print("  Quick: ~50-100MB (no CFG generation)")
        print("  Standard: ~100-300MB (selective CFG)")
        print("  Deep: ~300-800MB (full CFG, bounded)")

        print("\n" + "=" * 60)
        print("RECOMMENDATIONS")
        print("=" * 60)
        print("  • Use 'quick' strategy for first exploration")
        print("  • Use 'standard' strategy for daily development")
        print("  • Use 'deep' strategy for documentation/auditing")
        print("  • Enable streaming for large projects (>100 files)")
        print("  • Use incremental mode for CI/CD")

    finally:
        # Cleanup
        shutil.rmtree(project_path)
        print("\n[Cleaned up test project]")

    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
