#!/usr/bin/env python3
"""
CLI interface for logic2test.

Usage:
    python -m logic2test project.c2l.yaml --output tests/
    python -m logic2test project.c2l.hybrid.yaml --type integration
"""

import argparse
import sys
from pathlib import Path

from .generator import GenerationResult, GeneratorConfig, TestGenerator


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="logic2test",
        description="Generate tests from Code2Logic output files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate unit tests
    logic2test project.c2l.yaml -o tests/

    # Generate integration tests
    logic2test project.c2l.hybrid.yaml -o tests/ --type integration

    # Generate all test types
    logic2test project.c2l.yaml -o tests/ --type all

    # Include private methods
    logic2test project.c2l.yaml -o tests/ --include-private
""",
    )

    parser.add_argument("input", help="Path to Code2Logic output file (YAML, Hybrid, or TOON)")

    parser.add_argument(
        "-o",
        "--output",
        default="generated_tests",
        help="Output directory for generated tests (default: generated_tests)",
    )

    parser.add_argument(
        "-t",
        "--type",
        choices=["unit", "integration", "property", "all"],
        default="unit",
        help="Type of tests to generate (default: unit)",
    )

    parser.add_argument(
        "--framework",
        choices=["pytest", "unittest"],
        default="pytest",
        help="Test framework to use (default: pytest)",
    )

    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include private methods/functions (starting with _)",
    )

    parser.add_argument(
        "--include-dunder", action="store_true", help="Include dunder methods (__method__)"
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary of what can be generated without generating",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Create config
    config = GeneratorConfig(
        framework=args.framework,
        include_private=args.include_private,
        include_dunder=args.include_dunder,
    )

    # Create generator
    try:
        generator = TestGenerator(input_path, config)
    except Exception as e:
        print(f"Error parsing input file: {e}", file=sys.stderr)
        sys.exit(1)

    # Show summary if requested
    if args.summary:
        summary = generator.summary()
        print("\n=== Logic2Test Summary ===")
        print(f"Project: {summary['project_name']}")
        print(f"Modules: {summary['total_modules']}")
        print(f"Classes: {summary['total_classes']} ({summary['testable_classes']} testable)")
        print(f"Functions: {summary['total_functions']} ({summary['testable_functions']} testable)")
        print(f"Methods: {summary['total_methods']}")
        print(f"Dataclasses: {summary['dataclasses']}")
        return

    # Create output directory
    output_path = Path(args.output)

    results: list[GenerationResult] = []

    # Generate tests based on type
    if args.type in ("unit", "all"):
        if args.verbose:
            print("Generating unit tests...")
        result = generator.generate_unit_tests(
            output_path / "unit" if args.type == "all" else output_path
        )
        results.append(("unit", result))

    if args.type in ("integration", "all"):
        if args.verbose:
            print("Generating integration tests...")
        result = generator.generate_integration_tests(
            output_path / "integration" if args.type == "all" else output_path
        )
        results.append(("integration", result))

    if args.type in ("property", "all"):
        if args.verbose:
            print("Generating property tests...")
        result = generator.generate_property_tests(
            output_path / "property" if args.type == "all" else output_path
        )
        results.append(("property", result))

    # Print results
    print("\n=== Generation Results ===")

    total_files = 0
    total_tests = 0

    for test_type, result in results:
        print(f"\n{test_type.upper()}:")
        print(f"  Files generated: {result.files_generated}")
        print(f"  Tests generated: {result.tests_generated}")

        if result.classes_covered:
            print(f"  Classes covered: {result.classes_covered}")
        if result.functions_covered:
            print(f"  Functions covered: {result.functions_covered}")

        if args.verbose and result.output_files:
            print("  Output files:")
            for f in result.output_files:
                print(f"    - {f}")

        if result.errors:
            print("  Errors:")
            for e in result.errors:
                print(f"    - {e}")

        total_files += result.files_generated
        total_tests += result.tests_generated

    print(f"\n=== Total: {total_files} files, {total_tests} tests ===")


if __name__ == "__main__":
    main()
