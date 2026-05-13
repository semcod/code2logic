#!/usr/bin/env python3
"""
Fixed version: Optimize llm_prompt.md by creating a proper tree structure
"""

import re
from typing import Dict, List, Tuple


def parse_llm_prompt(
    file_path: str,
) -> Tuple[str, List[Tuple[str, List[str]]], List[Tuple[str, int, str]]]:
    """Parse the original llm_prompt.md file."""
    with open(file_path, "r") as f:
        content = f.read()

    # Extract overview
    overview_match = re.search(
        r"## Overview\n(.*?)(?=\n## |\n\n#|$)", content, re.DOTALL
    )
    overview = overview_match.group(1).strip() if overview_match else ""

    # Extract function calls - improved regex
    function_calls = []
    # Pattern matches: - **function.name** calls: func1, func2, func3
    call_pattern = r"^- \*\*([^*]+)\*\* calls: (.+?)$"

    lines = content.split("\n")
    for line in lines:
        match = re.match(call_pattern, line.strip())
        if match:
            func_name = match.group(1).strip()
            calls_info = match.group(2).strip()
            called_funcs = [call.strip() for call in calls_info.split(",")]
            function_calls.append((func_name, called_funcs))

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
    """Build a proper tree structure from function calls."""
    tree = {}

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
        if parts[-1] not in current:
            current[parts[-1]] = {}
        current[parts[-1]]["_calls"] = set(called_funcs)
        current[parts[-1]]["_full_name"] = func_name

    return tree


def build_class_tree(classes: List[Tuple[str, int, str]]) -> Dict:
    """Build a tree structure from classes."""
    tree = {}

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
        if parts[-1] not in current:
            current[parts[-1]] = {}
        current[parts[-1]]["methods"] = method_count
        current[parts[-1]]["inherits"] = inherits
        current[parts[-1]]["full_name"] = class_name

    return tree


def format_function_tree(tree: Dict, indent: int = 0) -> List[str]:
    """Format function tree structure as markdown."""
    lines = []
    indent_str = "  " * indent

    # Sort keys alphabetically, but put special keys (_calls, _full_name) at the end
    regular_keys = [k for k in tree.keys() if not k.startswith("_")]
    sorted_keys = sorted(regular_keys)

    for key in sorted_keys:
        value = tree[key]

        if isinstance(value, dict):
            # Check if this is a leaf function
            if "_calls" in value:
                # Function leaf - format the function call
                calls = sorted(value["_calls"])
                calls_str = ", ".join(calls)
                lines.append(
                    f"{indent_str}- **{value['_full_name']}** calls: {calls_str}"
                )
            else:
                # Module/package branch
                lines.append(f"{indent_str}- **{key}**")
                # Recursively format children
                child_lines = format_function_tree(value, indent + 1)
                lines.extend(child_lines)

    return lines


def format_class_tree(tree: Dict, indent: int = 0) -> List[str]:
    """Format class tree structure as markdown."""
    lines = []
    indent_str = "  " * indent

    # Sort keys alphabetically
    regular_keys = [k for k in tree.keys() if not k.startswith("_")]
    sorted_keys = sorted(regular_keys)

    for key in sorted_keys:
        value = tree[key]

        if isinstance(value, dict):
            # Check if this is a leaf class
            if "methods" in value:
                # Class leaf
                line = f"{indent_str}- **{value['full_name']}** ({value['methods']} methods)"
                if value["inherits"]:
                    line += f"\n{indent_str}  - inherits from: {value['inherits']}"
                lines.append(line)
            else:
                # Package branch
                lines.append(f"{indent_str}- **{key}**")
                # Recursively format children
                child_lines = format_class_tree(value, indent + 1)
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
    function_lines = format_function_tree(function_tree)
    lines.extend(function_lines)
    lines.append("")

    # Class Hierarchy (optimized tree structure)
    lines.append("## Class Hierarchy")
    lines.append("")
    class_lines = format_class_tree(class_tree)
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
    input_file = "/home/tom/github/wronai/nlp2cmd/debug/output/llm_prompt_original.md"
    output_file = "/home/tom/github/wronai/nlp2cmd/debug/output/llm_prompt_fixed.md"

    optimize_llm_prompt(input_file, output_file)
