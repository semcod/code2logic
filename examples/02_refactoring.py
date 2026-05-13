#!/usr/bin/env python3
"""
Refactoring Example - Find duplicates and quality issues.

Usage:
    python 02_refactoring.py
    python 02_refactoring.py /path/to/project
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from code2logic import (
    find_duplicates,
    analyze_quality,
)


def main():
    project_path = sys.argv[1] if len(sys.argv) > 1 else "code2logic/"

    print("=" * 60)
    print("CODE2LOGIC - REFACTORING ANALYSIS")
    print("=" * 60)

    # Find duplicates
    print(f"\n1. Finding Duplicates in {project_path}")
    print("-" * 40)

    duplicates = find_duplicates(project_path)
    print(f"   Found {len(duplicates)} duplicate groups")

    for dup in duplicates[:5]:
        print(f"\n   [{dup.hash}] {len(dup.functions)} occurrences")
        for func in dup.functions[:3]:
            print(f"      - {func}")

    # Quality analysis
    print("\n2. Quality Analysis")
    print("-" * 40)

    report = analyze_quality(project_path)
    print(f"   Quality issues: {len(report.quality_issues)}")
    print(f"   Security issues: {len(report.security_issues)}")

    for issue in report.quality_issues[:5]:
        icon = "🔴" if issue.severity == "high" else "🟡"
        print(f"   {icon} {issue.type}: {issue.location}")

    # Generate report
    print("\n3. Generate Report")
    print("-" * 40)

    markdown = report.to_markdown()
    print(f"   Report generated: {len(markdown)} chars")

    # Save report
    output = Path("examples/output/refactoring_report.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown)
    print(f"   Saved to: {output}")


if __name__ == "__main__":
    main()
