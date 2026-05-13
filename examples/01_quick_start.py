#!/usr/bin/env python3
"""
Quick Start Example - Basic code2logic usage.

Usage:
    python 01_quick_start.py
    python 01_quick_start.py /path/to/project
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from code2logic import (
    analyze_project,
    quick_analyze,
    GherkinGenerator,
    CSVGenerator,
)


def main():
    project_path = sys.argv[1] if len(sys.argv) > 1 else "code2logic/"

    print("=" * 60)
    print("CODE2LOGIC - QUICK START")
    print("=" * 60)

    # Quick analysis
    print(f"\n1. Quick Analysis of {project_path}")
    print("-" * 40)

    info = quick_analyze(project_path)
    print(f"   Project: {info['project']}")
    print(f"   Files: {info['files']}")
    print(f"   Lines: {info['lines']}")
    print(f"   Classes: {info['classes']}")
    print(f"   Functions: {info['functions']}")
    print(f"   Methods: {info['methods']}")

    # Full analysis
    print("\n2. Full Analysis")
    print("-" * 40)

    project = analyze_project(project_path)
    print(f"   Modules: {len(project.modules)}")
    print(f"   Languages: {project.languages}")

    # Generate outputs
    print("\n3. Generate Outputs")
    print("-" * 40)

    # Gherkin (best for LLM)
    gherkin = GherkinGenerator().generate(project, detail="minimal")
    print(f"   Gherkin: {len(gherkin)} chars")

    # CSV (compact)
    csv = CSVGenerator().generate(project, detail="minimal")
    print(f"   CSV: {len(csv)} chars")

    # Show sample
    print("\n4. Sample Gherkin Output")
    print("-" * 40)
    print(gherkin[:500])
    if len(gherkin) > 500:
        print(f"   ... ({len(gherkin) - 500} more chars)")


if __name__ == "__main__":
    main()
