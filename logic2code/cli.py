#!/usr/bin/env python3
"""
CLI interface for logic2code.

Usage:
    python -m logic2code project.c2l.yaml --output generated_src/
    python -m logic2code project.c2l.hybrid.yaml --stubs-only
"""

import argparse
import sys
from pathlib import Path

from .generator import CodeGenerator, GeneratorConfig


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="logic2code",
        description="Generate source code from Code2Logic output files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate Python code
    logic2code project.c2l.yaml -o generated_src/

    # Generate stubs only
    logic2code project.c2l.yaml -o generated_src/ --stubs-only

    # Generate specific modules
    logic2code project.c2l.yaml -o src/ --modules "analyzer.py,parsers.py"

    # Show summary
    logic2code project.c2l.yaml --summary

    # List available modules
    logic2code project.c2l.yaml --list-modules
""",
    )

    parser.add_argument("input", help="Path to Code2Logic output file (YAML, Hybrid, or TOON)")

    parser.add_argument(
        "-o",
        "--output",
        default="generated_code",
        help="Output directory for generated code (default: generated_code)",
    )

    parser.add_argument(
        "-l",
        "--language",
        choices=["python"],
        default="python",
        help="Target language (default: python)",
    )

    parser.add_argument(
        "--stubs-only",
        action="store_true",
        help="Generate stubs only (... instead of NotImplementedError)",
    )

    parser.add_argument("--no-docstrings", action="store_true", help="Skip docstring generation")

    parser.add_argument("--no-type-hints", action="store_true", help="Skip type hint generation")

    parser.add_argument("--no-init", action="store_true", help="Skip __init__.py generation")

    parser.add_argument(
        "--flat", action="store_true", help="Flat output structure (no subdirectories)"
    )

    parser.add_argument("--modules", help="Comma-separated list of modules to generate")

    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary of what can be generated without generating",
    )

    parser.add_argument("--list-modules", action="store_true", help="List available modules")

    parser.add_argument("--list-classes", action="store_true", help="List available classes")

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Create config
    config = GeneratorConfig(
        language=args.language,
        stubs_only=args.stubs_only,
        include_docstrings=not args.no_docstrings,
        include_type_hints=not args.no_type_hints,
        generate_init=not args.no_init,
        preserve_structure=not args.flat,
    )

    # Create generator
    try:
        generator = CodeGenerator(input_path, config)
    except Exception as e:
        print(f"Error parsing input file: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle list commands
    if args.list_modules:
        print("\n=== Available Modules ===")
        for module in generator.list_modules():
            print(f"  {module}")
        return

    if args.list_classes:
        print("\n=== Available Classes ===")
        for cls in generator.list_classes():
            print(f"  {cls}")
        return

    # Show summary if requested
    if args.summary:
        summary = generator.summary()
        print("\n=== Logic2Code Summary ===")
        print(f"Project: {summary['project_name']}")
        print(f"Total Modules: {summary['total_modules']}")
        print(f"  Python: {summary['python_modules']}")
        print(f"  Other: {summary['other_modules']}")
        print(f"Classes: {summary['total_classes']}")
        print(f"  Dataclasses: {summary['dataclasses']}")
        print(f"Functions: {summary['total_functions']}")
        print(f"Methods: {summary['total_methods']}")
        return

    # Parse modules filter
    modules_filter = None
    if args.modules:
        modules_filter = [m.strip() for m in args.modules.split(",")]

    # Generate code
    if args.verbose:
        print(f"Generating {args.language} code...")

    result = generator.generate(args.output, modules_filter)

    # Print results
    print("\n=== Generation Results ===")
    print(f"Files generated: {result.files_generated}")
    print(f"Classes generated: {result.classes_generated}")
    print(f"Functions generated: {result.functions_generated}")
    print(f"Lines generated: {result.lines_generated}")

    if args.verbose and result.output_files:
        print("\nOutput files:")
        for f in result.output_files[:20]:
            print(f"  - {f}")
        if len(result.output_files) > 20:
            print(f"  ... and {len(result.output_files) - 20} more")

    if result.errors:
        print("\nErrors:")
        for e in result.errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
