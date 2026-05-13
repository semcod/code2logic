#!/usr/bin/env python3
"""
Logic2Code Quickstart Example

Generate source code from Code2Logic output files.
"""

import sys
from pathlib import Path

# Add parent to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logic2code import CodeGenerator, GeneratorConfig


def example_basic_generation():
    """Basic code generation from a YAML file."""
    print("=== Basic Code Generation ===")

    # Check if sample file exists
    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print(f"Sample file not found: {sample_file}")
        print("Create a sample file or use code2logic to generate one:")
        print("  code2logic /path/to/project -f yaml -o sample_project.yaml")
        return

    # Create generator
    generator = CodeGenerator(sample_file)

    # Show summary
    summary = generator.summary()
    print(f"Modules: {summary['total_modules']}")
    print(f"Classes: {summary['total_classes']}")
    print(f"Functions: {summary['total_functions']}")

    # Generate code
    output_dir = Path(__file__).parent / "generated_code"
    result = generator.generate(output_dir)

    print(f"\nGenerated {result.files_generated} files")
    print(f"Lines: {result.lines_generated}")
    print(f"Output: {result.output_files}")


def example_with_config():
    """Code generation with custom configuration."""
    print("\n=== Custom Configuration ===")

    config = GeneratorConfig(
        language="python",
        stubs_only=False,
        include_docstrings=True,
        include_type_hints=True,
        generate_init=True,
        preserve_structure=True,
    )

    print(f"Language: {config.language}")
    print(f"Stubs only: {config.stubs_only}")
    print(f"Include docstrings: {config.include_docstrings}")
    print(f"Include type hints: {config.include_type_hints}")


def example_stubs_only():
    """Generate stubs only (no implementations)."""
    print("\n=== Stubs Only ===")

    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print("Sample file not found. Skipping...")
        return

    config = GeneratorConfig(stubs_only=True)
    generator = CodeGenerator(sample_file, config)

    output_dir = Path(__file__).parent / "generated_stubs"
    result = generator.generate(output_dir)

    print(f"Generated {result.files_generated} stub files")


def example_single_module():
    """Generate a single module."""
    print("\n=== Single Module ===")

    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print("Sample file not found. Skipping...")
        return

    generator = CodeGenerator(sample_file)

    # Generate specific module
    code = generator.generate_module("calculator.py")

    print("Generated code for calculator.py:")
    print("-" * 40)
    print(code[:500] + "..." if len(code) > 500 else code)


if __name__ == "__main__":
    print("Logic2Code Quickstart Examples\n")

    example_basic_generation()
    example_with_config()
    example_stubs_only()
    example_single_module()
