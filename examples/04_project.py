#!/usr/bin/env python3
"""
Project Reproduction Example - Multi-file projects.

Usage:
    python 04_project.py tests/samples/
    python 04_project.py code2logic/ --parallel
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from code2logic import reproduce_project, compare_codebases


def main():
    parser = argparse.ArgumentParser(description="Project reproduction")
    parser.add_argument("project", nargs="?", default="tests/samples/")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--parallel", "-p", action="store_true")
    parser.add_argument("--compare", help="Compare with another project")
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip LLM generation (template/AST mode)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("CODE2LOGIC - PROJECT")
    print("=" * 60)

    # Compare projects
    if args.compare:
        print(f"\nComparing: {args.project} vs {args.compare}")
        result = compare_codebases(args.project, args.compare)

        print(
            f"\n  Project 1: {result['project1']['files']} files, {result['project1']['elements']} elements"
        )
        print(
            f"  Project 2: {result['project2']['files']} files, {result['project2']['elements']} elements"
        )
        print(f"  Similarity: {result['similarity_percent']}%")
        print(f"  Common: {result['common_elements']}")
        return

    # Reproduce project
    print(f"\nReproducing: {args.project}")

    result = reproduce_project(
        args.project,
        output_dir=args.output or "examples/output/project",
        parallel=args.parallel,
        use_llm=not args.no_llm,
    )

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"  Files:        {result.total_files}")
    print(f"  Successful:   {result.successful_files}")
    print(f"  Compression:  {result.avg_compression:.2f}x")
    print(f"  Similarity:   {result.avg_similarity:.1f}%")

    if result.by_language:
        print("\n  By Language:")
        for lang, data in result.by_language.items():
            print(f"    {lang}: {data['similarity']:.1f}%")


if __name__ == "__main__":
    main()
