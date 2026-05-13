#!/usr/bin/env python3
"""
Metrics Analysis Example - Detailed reproduction quality analysis.

Uses the standardized ReproductionMetrics API.

Usage:
    python 06_metrics.py tests/samples/sample_dataclasses.py
    python 06_metrics.py tests/samples/sample_class.py --verbose
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
    ReproductionMetrics,
    get_client,
    generate_file_gherkin,
)
from code2logic.reproduction import extract_code_block


def analyze_file(source_path: str, verbose: bool = False, no_llm: bool = False):
    """Analyze single file with detailed metrics."""
    path = Path(source_path)
    original = path.read_text()

    print(f"\n{'=' * 60}")
    print(f"METRICS ANALYSIS: {source_path}")
    print(f"{'=' * 60}")

    # Generate spec
    spec = generate_file_gherkin(source_path)
    print(f"Spec size: {len(spec)} chars ({len(spec) // 4} tokens)")

    # Reproduce
    if no_llm:
        generated = _template_generate(spec)
        print("Using template generation (--no-llm)")
    else:
        try:
            client = get_client()
            provider_name = (
                getattr(client, "provider", None) or client.__class__.__name__
            )
            print(f"Selected: {provider_name}")
            print(f"Model: {getattr(client, 'model', 'default')}")
            prompt = f"Generate Python code from this Gherkin spec:\n\n{spec}\n\nOutput only code."
            response = client.generate(prompt, max_tokens=4000)
            generated = extract_code_block(response)
            print(f"Generated: {len(generated)} chars")
        except Exception as e:
            print(f"LLM failed: {e}, using template")
            generated = _template_generate(spec)

    # Analyze
    metrics = ReproductionMetrics(verbose=verbose)
    result = metrics.analyze(
        original, generated, spec, format_name="gherkin", source_file=source_path
    )

    # Print results
    print(f"\n📊 Overall: {result.overall_score:.1f}% ({result.quality_grade})")

    print("\n📝 Text Metrics:")
    print(f"   Cosine Similarity:  {result.text.cosine_similarity:.1f}%")
    print(f"   Jaccard Similarity: {result.text.jaccard_similarity:.1f}%")

    print("\n🏗️ Structural:")
    print(
        f"   Classes:   {result.structural.classes_original} → {result.structural.classes_generated}"
    )
    print(
        f"   Functions: {result.structural.functions_original} → {result.structural.functions_generated}"
    )
    print(f"   Score:     {result.structural.structural_score:.1f}%")

    print("\n🎯 Semantic:")
    print(f"   Naming:    {result.semantic.naming_similarity:.1f}%")
    print(f"   Intent:    {result.semantic.intent_score:.1f}%")

    print("\n📦 Efficiency:")
    print(f"   Compression: {result.format.compression_ratio:.2f}x")

    if result.recommendations:
        print("\n💡 Recommendations:")
        for rec in result.recommendations[:3]:
            print(f"   • {rec}")

    return result


def _template_generate(spec: str) -> str:
    """Simple template fallback."""
    import re

    classes = list(set(re.findall(r"class (\w+)", spec)))[:3]

    code = "from dataclasses import dataclass\nfrom typing import Optional, List\n\n"
    for cls in classes:
        if cls.isidentifier() and cls not in ["Given", "When", "Then"]:
            code += f"@dataclass\nclass {cls}:\n    pass\n\n"
    return code


def main():
    parser = argparse.ArgumentParser(description="Reproduction metrics analysis")
    parser.add_argument(
        "source", nargs="?", default="tests/samples/sample_dataclasses.py"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    analyze_file(args.source, args.verbose, args.no_llm)


if __name__ == "__main__":
    main()
