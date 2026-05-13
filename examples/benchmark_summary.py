#!/usr/bin/env python3
"""Print benchmark summary from JSON result files."""

import json
import os
import sys


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def _token_estimate_bytes(n: int) -> int:
    return n // 4


def _artifact_row(label: str, path: str) -> str:
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    return f"{label:<28} {_fmt_bytes(size):>10} {_token_estimate_bytes(size):>10,}  {os.path.basename(path)}"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "examples/output"

    files = {
        "Format": os.path.join(out, "benchmark_format.json"),
        "Token": os.path.join(out, "benchmark_token.json"),
        "Project": os.path.join(out, "benchmark_project.json"),
        "Function": os.path.join(out, "benchmark_function.json"),
    }

    print()
    print(
        f"{'Benchmark':<12} {'Files':>6} {'Avg Score':>10} "
        f"{'Syntax OK':>10} {'Runs OK':>10} {'Best Format':>14} {'Time':>8}"
    )
    print("-" * 75)

    for name, path in files.items():
        if not os.path.exists(path):
            continue
        d = json.load(open(path))
        if d.get("benchmark_type") == "function":
            fr = d.get("function_results") or []
            total = d.get("total_functions", len(fr))
            sims = [x.get("similarity", 0.0) for x in fr]
            avg_sim = sum(sims) / len(sims) if sims else 0.0
            syn = (
                (sum(1 for x in fr if x.get("syntax_ok")) / len(fr) * 100)
                if fr
                else 0.0
            )
            print(
                f"{name:<12} {total:>6} "
                f"{avg_sim:>9.1f}% "
                f"{syn:>9.0f}% "
                f"{'-':>9} "
                f"{'-':>14} "
                f"{d.get('total_time', 0):>7.1f}s"
            )
        else:
            total = d.get("total_files", "-")
            print(
                f"{name:<12} {total:>6} "
                f"{d.get('avg_score', 0):>9.1f}% "
                f"{d.get('syntax_ok_rate', 0):>9.0f}% "
                f"{d.get('runs_ok_rate', 0):>9.0f}% "
                f"{d.get('best_format', '-'):>14} "
                f"{d.get('total_time', 0):>7.1f}s"
            )

    print()

    fmt_path = os.path.join(out, "benchmark_format.json")
    if os.path.exists(fmt_path):
        d = json.load(open(fmt_path))
        scores = d.get("format_scores", {})
        if scores:
            print("Format scores:")
            for fmt, sc in sorted(scores.items(), key=lambda x: -x[1]):
                bar = "\u2588" * int(sc / 2)
                print(f"  {fmt:<10} {sc:>6.1f}%  {bar}")
            print()

    # Self-analysis artifacts (produced by `make benchmark-toon`)
    candidates = [
        ("TOON (project)", os.path.join(out, "project.toon")),
        ("TOON schema (project)", os.path.join(out, "project.toon-schema.json")),
        ("TOON function-logic", os.path.join(out, "function.toon")),
        ("Function-logic schema", os.path.join(out, "function-schema.json")),
        ("YAML (project)", os.path.join(out, "project.yaml")),
        ("JSON (project)", os.path.join(out, "project.json")),
        ("Markdown (project)", os.path.join(out, "project.md")),
        ("Compact (project)", os.path.join(out, "project.txt")),
        ("CSV (project)", os.path.join(out, "project.csv")),
    ]

    rows = []
    seen = set()
    for label, path in candidates:
        if path in seen:
            continue
        seen.add(path)
        row = _artifact_row(label, path)
        if row:
            rows.append(row)

    if rows:
        print("Self-analysis artifacts (size / ~tokens):")
        print(f"{'Artifact':<28} {'Size':>10} {'~Tokens':>10}  File")
        print("-" * 70)
        for row in rows:
            print(row)
        print()


if __name__ == "__main__":
    main()
