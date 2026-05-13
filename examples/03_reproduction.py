#!/usr/bin/env python3
"""
Code Reproduction Example - Generate code from logic.

Usage:
    python 03_reproduction.py tests/samples/sample_dataclasses.py
    python 03_reproduction.py code2logic/models.py --no-llm
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

from code2logic import (
    reproduce_file,
    generate_file_gherkin,
)


def main():
    parser = argparse.ArgumentParser(description="Code reproduction")
    parser.add_argument(
        "source", nargs="?", default="tests/samples/sample_dataclasses.py"
    )
    parser.add_argument("--output", "-o", default="examples/output/reproduction")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM generation")
    parser.add_argument(
        "--show-spec", action="store_true", help="Show specification only"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("CODE2LOGIC - REPRODUCTION")
    print("=" * 60)

    print(f"\nSource: {args.source}")

    # Show specification only
    if args.show_spec:
        spec = generate_file_gherkin(args.source)
        print(f"\nGherkin Specification ({len(spec)} chars):")
        print("-" * 40)
        print(spec[:1500])
        if len(spec) > 1500:
            print(f"\n... ({len(spec) - 1500} more chars)")
        return

    # Full reproduction
    print("\nReproducing...")

    result = reproduce_file(
        args.source,
        output_dir=args.output,
        use_llm=not args.no_llm,
    )

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print("=" * 60)
    print(f"  Language:     {result['source_language']}")
    print(f"  Source:       {result['source_chars']} chars")
    print(f"  Logic:        {result['logic_chars']} chars")
    print(f"  Generated:    {result['generated_chars']} chars")
    print(f"  Compression:  {result['compression_ratio']:.2f}x")
    print(f"  Similarity:   {result['similarity']:.1f}%")
    print(f"\n  Output: {args.output}/")


if __name__ == "__main__":
    main()
