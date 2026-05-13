#!/usr/bin/env python3
"""
Optimize llm_prompt.md by creating a tree structure and sorting by names
to reduce file size and improve readability.
"""

import re
from collections import defaultdict
from typing import Dict, List, Tuple


def parse_llm_prompt(file_path: str) -> Tuple[Dict, List, List]:
    """Parse the original llm_prompt.md file."""
    with open(file_path, "r") as f:
        content = f.read()

    # Extract overview
    overview_match = re.search(
        r"## Overview\n(.*?)(?=\n## |\n\n#|$)", content, re.DOTALL
    )
    overview = overview_match.group(1).strip() if overview_match else ""

    # Extract function calls
    function_calls = []
    call_pattern = r"- \*\*([^*]+)\*\* calls: (.+?)(?=\n- \*\*|\n\n##|\Z)"
    calls = re.findall(call_pattern, content, re.DOTALL)

    for func_name, calls_info in calls:
        # Parse called functions
        called_funcs = [call.strip() for call in calls_info.split(",")]
        function_calls.append((func_name.strip(), called_funcs))

    # Extract classes
    classes = []
    class_pattern = (
        r"- \*\*([^\*]+)\*\* \((\d+) methods\)(?:\s*-\s*inherits from:\s*(.+))?"
    )
    class_matches = re.findall(class_pattern, content)

    for class_name, method_count, inherits in class_matches:
        classes.append(
            (
                class_name.strip(),
                int(method_count),
                inherits.strip() if inherits else None,
            )
        )

    return overview, function_calls, classes


def build_function_tree(function_calls: List[Tuple[str, List[str]]]) -> Dict:
    """Build a tree structure from function calls."""
    tree = defaultdict(lambda: defaultdict(set))

    for func_name, called_funcs in function_calls:
        # Split the full function name into parts
        parts = func_name.split(".")

        # Build the tree path
        current = tree
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]

        # Add the leaf (actual function)
        current[parts[-1]] = {"_calls": set(called_funcs), "_full_name": func_name}

    return tree


def build_class_tree(classes: List[Tuple[str, int, str]]) -> Dict:
    """Build a tree structure from classes."""
    tree = defaultdict(lambda: defaultdict(dict))

    for class_name, method_count, inherits in classes:
        # Split the full class name into parts
        parts = class_name.split(".")

        # Build the tree path
        current = tree
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]

        # Add the leaf (actual class)
        current[parts[-1]] = {
            "methods": method_count,
            "inherits": inherits,
            "full_name": class_name,
        }

    return tree


def format_tree(tree: Dict, indent: int = 0, is_function: bool = False) -> List[str]:
    """Format tree structure as markdown."""
    lines = []
    indent_str = "  " * indent

    # Sort keys alphabetically
    sorted_keys = sorted(k for k in tree.keys() if not k.startswith("_"))

    for key in sorted_keys:
        value = tree[key]

        if isinstance(value, dict):
            # Check if this is a leaf node
            if is_function and "_calls" in value:
                # Function leaf
                lines.append(
                    f"{indent_str}- **{value['_full_name']}** calls: {', '.join(sorted(value['_calls']))}"
                )
            elif not is_function and "methods" in value:
                # Class leaf
                line = f"{indent_str}- **{value['full_name']}** ({value['methods']} methods)"
                if value["inherits"]:
                    line += f"\n{indent_str}  - inherits from: {value['inherits']}"
                lines.append(line)
            else:
                # Branch node - show the module/package name
                lines.append(f"{indent_str}- **{key}**")
                # Recursively format children
                child_lines = format_tree(value, indent + 1, is_function)
                lines.extend(child_lines)

    return lines


def optimize_llm_prompt(input_file: str, output_file: str):
    """Main optimization function."""
    print(f"Reading {input_file}...")
    overview, function_calls, classes = parse_llm_prompt(input_file)

    print("Building trees...")
    function_tree = build_function_tree(function_calls)
    class_tree = build_class_tree(classes)

    print("Generating optimized output...")
    lines = []

    # Header
    lines.append("# System Analysis Report")
    lines.append("")
    lines.append("## Overview")
    lines.append(overview)
    lines.append("")

    # Function Call Graph (optimized tree structure)
    lines.append("## Function Call Graph")
    lines.append("")
    function_lines = format_tree(function_tree, is_function=True)
    lines.extend(function_lines)
    lines.append("")

    # Class Hierarchy (optimized tree structure)
    lines.append("## Class Hierarchy")
    lines.append("")
    class_lines = format_tree(class_tree, is_function=False)
    lines.extend(class_lines)
    lines.append("")

    # Keep the original guidelines
    lines.append("## Reverse Engineering Guidelines")
    lines.append("")
    lines.append("1. Preserve the call graph structure")
    lines.append("2. Maintain data dependencies")
    lines.append("3. Recreate class hierarchies")
    lines.append("4. Implement control flow patterns")

    # Write optimized file
    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    # Calculate size reduction
    original_size = len(open(input_file, "r").read())
    optimized_size = len("\n".join(lines))
    reduction = (original_size - optimized_size) / original_size * 100

    print("Optimization complete!")
    print(f"Original size: {original_size:,} bytes")
    print(f"Optimized size: {optimized_size:,} bytes")
    print(f"Size reduction: {reduction:.1f}%")
    print(f"Functions organized: {len(function_calls)}")
    print(f"Classes organized: {len(classes)}")


if __name__ == "__main__":
    input_file = "/home/tom/github/wronai/nlp2cmd/debug/output/llm_prompt.md"
    output_file = "/home/tom/github/wronai/nlp2cmd/debug/output/llm_prompt_optimized.md"

    optimize_llm_prompt(input_file, output_file)
