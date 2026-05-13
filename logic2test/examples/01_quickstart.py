#!/usr/bin/env python3
"""
Logic2Test Quickstart Example

Generate test scaffolds from Code2Logic output files.
"""

import sys
from pathlib import Path

# Add parent to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logic2test import GeneratorConfig, TestGenerator


def example_basic_generation():
    """Basic test generation from a YAML file."""
    print("=== Basic Test Generation ===")

    # Check if sample file exists
    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print(f"Sample file not found: {sample_file}")
        print("Create a sample file or use code2logic to generate one:")
        print("  code2logic /path/to/project -f yaml -o sample_project.yaml")
        return

    # Create generator
    generator = TestGenerator(sample_file)

    # Show summary
    summary = generator.summary()
    print(f"Modules: {summary['total_modules']}")
    print(f"Classes: {summary['testable_classes']}")
    print(f"Functions: {summary['testable_functions']}")

    # Generate tests
    output_dir = Path(__file__).parent / "generated_tests"
    result = generator.generate_unit_tests(output_dir)

    print(f"\nGenerated {result.tests_generated} tests")
    print(f"Output files: {result.output_files}")


def example_with_config():
    """Test generation with custom configuration."""
    print("\n=== Custom Configuration ===")

    config = GeneratorConfig(
        framework="pytest",
        include_private=True,
        include_dunder=False,
        max_tests_per_file=100,
        generate_class_tests=True,
        generate_function_tests=True,
        generate_dataclass_tests=True,
    )

    print(f"Framework: {config.framework}")
    print(f"Include private: {config.include_private}")
    print(f"Max tests per file: {config.max_tests_per_file}")


def example_generate_all_types():
    """Generate all test types."""
    print("\n=== All Test Types ===")

    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print("Sample file not found. Skipping...")
        return

    generator = TestGenerator(sample_file)
    output_dir = Path(__file__).parent / "generated_tests_full"

    # Generate all test types
    result = generator.generate_all(output_dir)

    print(f"Tests generated: {result.tests_generated}")
    print(f"Files created: {result.files_generated}")

    # Show structure
    if output_dir.exists():
        print("\nGenerated structure:")
        for path in sorted(output_dir.rglob("*.py")):
            print(f"  {path.relative_to(output_dir)}")


if __name__ == "__main__":
    print("Logic2Test Quickstart Examples\n")

    example_basic_generation()
    example_with_config()
    example_generate_all_types()
