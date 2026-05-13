#!/usr/bin/env python3
"""
Logic2Code LLM-Enhanced Generation Example

Using LLM to generate implementations from logic specifications.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logic2code import CodeGenerator, GeneratorConfig


def example_llm_generation():
    """Generate code with LLM-enhanced implementations."""
    print("=== LLM-Enhanced Code Generation ===")

    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print("Sample file not found. Skipping...")
        return

    # Enable LLM generation
    config = GeneratorConfig(
        use_llm=True,
        llm_provider="openrouter",  # or 'ollama', 'groq', etc.
        include_docstrings=True,
        include_type_hints=True,
    )

    print(f"LLM enabled: {config.use_llm}")
    print(f"Provider: {config.llm_provider}")

    try:
        generator = CodeGenerator(sample_file, config)

        output_dir = Path(__file__).parent / "generated_code_llm"
        result = generator.generate(output_dir)

        print(f"\nGenerated {result.files_generated} files with LLM")
        print(f"Lines: {result.lines_generated}")

        if result.errors:
            print(f"Errors: {result.errors}")
    except Exception as e:
        print(f"LLM generation failed: {e}")
        print("Make sure you have lolm installed and configured:")
        print("  pip install lolm")
        print("  export OPENROUTER_API_KEY='your-key'")


def example_hybrid_generation():
    """Hybrid generation: stubs + LLM for complex functions."""
    print("\n=== Hybrid Generation ===")
    print("This approach generates stubs first, then uses LLM selectively.")

    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print("Sample file not found. Skipping...")
        return

    # Step 1: Generate stubs
    stub_config = GeneratorConfig(stubs_only=True)
    stub_generator = CodeGenerator(sample_file, stub_config)

    output_dir = Path(__file__).parent / "generated_hybrid"
    stub_result = stub_generator.generate(output_dir)

    print(f"Step 1: Generated {stub_result.files_generated} stub files")

    # Step 2: Use LLM to implement specific functions
    print("Step 2: LLM would implement complex functions...")
    print("(This requires manual selection of which functions to enhance)")


def example_compare_outputs():
    """Compare stub vs LLM-generated outputs."""
    print("\n=== Compare Outputs ===")

    sample_file = Path(__file__).parent / "sample_project.yaml"
    if not sample_file.exists():
        print("Sample file not found. Skipping...")
        return

    # Stub generation
    stub_config = GeneratorConfig(stubs_only=True)
    stub_generator = CodeGenerator(sample_file, stub_config)
    stub_code = stub_generator.generate_module("calculator.py")

    print("Stub output (excerpt):")
    print("-" * 40)
    lines = stub_code.split("\n")[:20]
    print("\n".join(lines))

    # Full generation (without LLM)
    full_config = GeneratorConfig(stubs_only=False)
    full_generator = CodeGenerator(sample_file, full_config)
    full_code = full_generator.generate_module("calculator.py")

    print("\nFull output (excerpt):")
    print("-" * 40)
    lines = full_code.split("\n")[:20]
    print("\n".join(lines))


if __name__ == "__main__":
    print("Logic2Code LLM-Enhanced Examples\n")

    example_llm_generation()
    example_hybrid_generation()
    example_compare_outputs()
