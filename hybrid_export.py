#!/usr/bin/env python3
"""
Hybrid export strategy combining separated and split approaches.

First separates orphans from consolidated, then splits each into multiple files.
"""

import yaml
from pathlib import Path
from collections import defaultdict


def hybrid_export_strategy(result, output_base_path):
    """Implement hybrid export: separate orphans + split files."""

    print("🔄 HYBRID EXPORT STRATEGY")
    print("   Step 1: Separate orphans from consolidated")
    print("   Step 2: Split each into multiple files")
    print()

    base_path = Path(output_base_path)
    hybrid_path = base_path / "output_hybrid"
    hybrid_path.mkdir(exist_ok=True)

    # Step 1: Separate orphans from consolidated
    print("📋 Step 1: Separating orphans from consolidated...")
    separated_data = separate_orphans_and_consolidated(result)

    # Step 2: Split each category
    print("✂️  Step 2: Splitting each category into files...")
    split_consolidated(hybrid_path, separated_data["consolidated"])
    split_orphans(hybrid_path, separated_data["orphans"])

    # Create index
    create_hybrid_index(hybrid_path, separated_data)

    print(f"✓ Hybrid export complete: {hybrid_path}")
    return hybrid_path


def separate_orphans_and_consolidated(result):
    """Separate functions into orphans and consolidated."""

    consolidated = {"functions": {}, "nodes": {}, "stats": {"functions": 0, "nodes": 0}}

    orphans = {"functions": {}, "nodes": {}, "stats": {"functions": 0, "nodes": 0}}

    # Separate functions
    for func_name, func in result.functions.items():
        # Check if function is orphan (no calls and no called_by)
        is_orphan = len(func.calls) == 0 and len(func.called_by) == 0

        target = orphans if is_orphan else consolidated
        target["functions"][func_name] = func
        target["stats"]["functions"] += 1

    # Separate nodes
    for node_name, node in result.nodes.items():
        # Check if node is orphan
        is_orphan = (
            len(getattr(node, "calls", [])) == 0
            and len(getattr(node, "called_by", [])) == 0
        )

        target = orphans if is_orphan else consolidated
        target["nodes"][node_name] = node
        target["stats"]["nodes"] += 1

    print(
        f"  • Consolidated: {consolidated['stats']['functions']} functions, {consolidated['stats']['nodes']} nodes"
    )
    print(
        f"  • Orphans: {orphans['stats']['functions']} functions, {orphans['stats']['nodes']} nodes"
    )

    return {"consolidated": consolidated, "orphans": orphans}


def split_consolidated(base_path, consolidated_data):
    """Split consolidated data into multiple files."""

    consolidated_path = base_path / "consolidated"
    consolidated_path.mkdir(exist_ok=True)

    # Split functions by module
    functions_by_module = defaultdict(dict)
    for func_name, func in consolidated_data["functions"].items():
        module = func_name.rsplit(".", 1)[0] if "." in func_name else "root"
        functions_by_module[module][func_name] = func

    # Save functions by module
    for module, functions in functions_by_module.items():
        safe_module_name = module.replace(".", "_").replace("/", "_")
        file_path = consolidated_path / f"functions_{safe_module_name}.yaml"

        with open(file_path, "w") as f:
            yaml.dump(
                {
                    "module": module,
                    "type": "functions",
                    "count": len(functions),
                    "functions": {
                        name: func.to_dict() for name, func in functions.items()
                    },
                },
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    # Split nodes by type
    nodes_by_type = defaultdict(dict)
    for node_name, node in consolidated_data["nodes"].items():
        node_type = getattr(node, "type", "UNKNOWN")
        nodes_by_type[node_type][node_name] = node

    # Save nodes by type
    for node_type, nodes in nodes_by_type.items():
        file_path = consolidated_path / f"nodes_{node_type.lower()}.yaml"

        with open(file_path, "w") as f:
            yaml.dump(
                {
                    "type": node_type,
                    "count": len(nodes),
                    "nodes": {
                        name: getattr(node, "to_dict", lambda: node.__dict__)()
                        for name, node in nodes.items()
                    },
                },
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    # Save consolidated summary
    with open(consolidated_path / "summary.yaml", "w") as f:
        yaml.dump(
            {
                "category": "consolidated",
                "stats": consolidated_data["stats"],
                "modules": list(functions_by_module.keys()),
                "node_types": list(nodes_by_type.keys()),
            },
            f,
            default_flow_style=False,
            sort_keys=False,
        )

    print(
        f"  • Consolidated split into {len(functions_by_module)} module files + {len(nodes_by_type)} type files"
    )


def split_orphans(base_path, orphans_data):
    """Split orphans data into multiple files."""

    orphans_path = base_path / "orphans"
    orphans_path.mkdir(exist_ok=True)

    # Group orphans by patterns
    orphan_functions = orphans_data["functions"]
    orphan_nodes = orphans_data["nodes"]

    # Split functions by first letter of name
    functions_by_letter = defaultdict(dict)
    for func_name, func in orphan_functions.items():
        first_letter = func_name.split(".")[-1][0].upper() if func_name else "OTHER"
        functions_by_letter[first_letter][func_name] = func

    # Save functions by letter
    for letter, functions in functions_by_letter.items():
        file_path = orphans_path / f"functions_{letter.lower()}.yaml"

        with open(file_path, "w") as f:
            yaml.dump(
                {
                    "letter": letter,
                    "type": "orphan_functions",
                    "count": len(functions),
                    "functions": {
                        name: func.to_dict() for name, func in functions.items()
                    },
                },
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    # Split nodes by module
    nodes_by_module = defaultdict(dict)
    for node_name, node in orphan_nodes.items():
        module = node_name.rsplit(".", 1)[0] if "." in node_name else "root"
        nodes_by_module[module][node_name] = node

    # Save nodes by module
    for module, nodes in nodes_by_module.items():
        safe_module_name = module.replace(".", "_").replace("/", "_")
        file_path = orphans_path / f"nodes_{safe_module_name}.yaml"

        with open(file_path, "w") as f:
            yaml.dump(
                {
                    "module": module,
                    "type": "orphan_nodes",
                    "count": len(nodes),
                    "nodes": {
                        name: getattr(node, "to_dict", lambda: node.__dict__)()
                        for name, node in nodes.items()
                    },
                },
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    # Save orphans summary
    with open(orphans_path / "summary.yaml", "w") as f:
        yaml.dump(
            {
                "category": "orphans",
                "stats": orphans_data["stats"],
                "function_groups": list(functions_by_letter.keys()),
                "node_modules": list(nodes_by_module.keys()),
            },
            f,
            default_flow_style=False,
            sort_keys=False,
        )

    print(
        f"  • Orphans split into {len(functions_by_letter)} letter groups + {len(nodes_by_module)} module files"
    )


def create_hybrid_index(base_path, separated_data):
    """Create comprehensive index for hybrid export."""

    index_data = {
        "export_type": "hybrid",
        "description": "Separated orphans + split files",
        "structure": {
            "consolidated": {
                "path": "consolidated/",
                "description": "Connected functions and nodes",
                "stats": separated_data["consolidated"]["stats"],
            },
            "orphans": {
                "path": "orphans/",
                "description": "Isolated functions and nodes",
                "stats": separated_data["orphans"]["stats"],
            },
        },
        "total_stats": {
            "functions": separated_data["consolidated"]["stats"]["functions"]
            + separated_data["orphans"]["stats"]["functions"],
            "nodes": separated_data["consolidated"]["stats"]["nodes"]
            + separated_data["orphans"]["stats"]["nodes"],
        },
        "generated_files": list_files(base_path),
    }

    with open(base_path / "index.yaml", "w") as f:
        yaml.dump(index_data, f, default_flow_style=False, sort_keys=False)

    print(f"  • Index created: {base_path / 'index.yaml'}")


def list_files(base_path):
    """List all generated files."""
    files = []

    for category in ["consolidated", "orphans"]:
        cat_path = base_path / category
        if cat_path.exists():
            for file_path in cat_path.rglob("*.yaml"):
                relative_path = file_path.relative_to(base_path)
                files.append(str(relative_path))

    return sorted(files)


def run_hybrid_export():
    """Run hybrid export with current analysis."""

    # Import and run analysis
    import sys

    sys.path.insert(0, ".")
    from code2flow import ProjectAnalyzer, FAST_CONFIG

    print("🔍 Running analysis...")
    analyzer = ProjectAnalyzer(FAST_CONFIG)
    result = analyzer.analyze_project("../src/nlp2cmd")

    # Run hybrid export
    hybrid_path = hybrid_export_strategy(result, "./")

    # Show summary
    print("\n📊 HYBRID EXPORT SUMMARY:")
    print(f"📁 Output directory: {hybrid_path}")

    # Count files
    total_files = len(list(hybrid_path.rglob("*.yaml")))
    consolidated_files = (
        len(list((hybrid_path / "consolidated").rglob("*.yaml")))
        if (hybrid_path / "consolidated").exists()
        else 0
    )
    orphan_files = (
        len(list((hybrid_path / "orphans").rglob("*.yaml")))
        if (hybrid_path / "orphans").exists()
        else 0
    )

    print("📈 File count:")
    print(f"  • Total files: {total_files}")
    print(f"  • Consolidated: {consolidated_files}")
    print(f"  • Orphans: {orphan_files}")
    print("  • Index: 1")

    # Show structure
    print("\n🏗️  Structure:")
    print("output_hybrid/")
    print("├── index.yaml")
    print("├── consolidated/")
    print("│   ├── summary.yaml")
    print("│   ├── functions_*.yaml (by module)")
    print("│   └── nodes_*.yaml (by type)")
    print("└── orphans/")
    print("    ├── summary.yaml")
    print("    ├── functions_*.yaml (by letter)")
    print("    └── nodes_*.yaml (by module)")

    return hybrid_path


if __name__ == "__main__":
    run_hybrid_export()
