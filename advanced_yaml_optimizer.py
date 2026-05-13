#!/usr/bin/env python3
"""
Advanced YAML optimization analysis.

Analyzes current files and identifies additional optimization opportunities.
"""

import yaml
from pathlib import Path
from collections import Counter


def analyze_yaml_optimization():
    """Analyze YAML files for further optimization opportunities."""

    print("🔍 ANALYZING YAML OPTIMIZATION OPPORTUNITIES")
    print("=" * 50)

    # Load current files
    main_file = Path("output_structures/data_structures_main.yaml")
    flow_file = Path("output_structures/data_flow_graph.yaml")

    with open(main_file, "r") as f:
        main_data = yaml.safe_load(f)

    with open(flow_file, "r") as f:
        flow_data = yaml.safe_load(f)

    print("📁 Current files:")
    print(f"  • Main: {main_file.stat().st_size / 1024:.1f}K")
    print(f"  • Flow: {flow_file.stat().st_size / 1024:.1f}K")
    print()

    # Analyze main data structure
    print("🔍 MAIN DATA ANALYSIS:")
    analyze_main_data(main_data)

    # Analyze flow graph
    print("\n🔍 FLOW GRAPH ANALYSIS:")
    analyze_flow_graph(flow_data)

    # Identify optimization opportunities
    print("\n💡 OPTIMIZATION OPPORTUNITIES:")
    opportunities = identify_optimizations(main_data, flow_data)

    # Apply optimizations
    print("\n⚡ APPLYING OPTIMIZATIONS:")
    optimized_main, optimized_flow = apply_optimizations(
        main_data, flow_data, opportunities
    )

    # Save optimized files
    save_optimized_files(optimized_main, optimized_flow)

    # Show comparison
    show_comparison(main_data, flow_data, optimized_main, optimized_flow)


def analyze_main_data(data):
    """Analyze main data structure for optimization opportunities."""

    # Analyze data_types
    if "data_types" in data:
        data_types = data["data_types"]
        print(f"  • Data types: {len(data_types)}")

        # Check for redundant information
        total_functions = sum(len(dt.get("functions", [])) for dt in data_types)
        print(f"  • Total function references: {total_functions}")

        # Check for empty lists
        empty_params = sum(1 for dt in data_types if not dt.get("parameter_types"))
        empty_returns = sum(1 for dt in data_types if not dt.get("return_types"))
        print(f"  • Empty parameter_types: {empty_params}/{len(data_types)}")
        print(f"  • Empty return_types: {empty_returns}/{len(data_types)}")

    # Analyze process_patterns
    if "process_patterns" in data:
        patterns = data["process_patterns"]
        print(f"  • Process patterns: {len(patterns)}")

        total_pattern_functions = sum(len(p.get("functions", [])) for p in patterns)
        print(f"  • Total pattern functions: {total_pattern_functions}")

    # Analyze optimization_analysis
    if "optimization_analysis" in data:
        opt = data["optimization_analysis"]
        print(f"  • Optimization sections: {len(opt)}")

        for section, content in opt.items():
            if isinstance(content, list):
                print(f"    - {section}: {len(content)} items")


def analyze_flow_graph(data):
    """Analyze flow graph for optimization opportunities."""

    if "nodes" in data:
        nodes = data["nodes"]
        print(f"  • Nodes: {len(nodes)}")

        # Analyze node properties
        hub_nodes = sum(1 for n in nodes.values() if n.get("hub", False))
        empty_types = sum(1 for n in nodes.values() if not n.get("types", []))
        zero_connections = sum(
            1
            for n in nodes.values()
            if n.get("in_deg", 0) == 0 and n.get("out_deg", 0) == 0
        )

        print(f"  • Hub nodes: {hub_nodes}")
        print(f"  • Empty types: {empty_types}")
        print(f"  • Zero connections: {zero_connections}")

    if "edges" in data:
        edges = data["edges"]
        print(f"  • Edges: {len(edges)}")

        # Analyze edge properties
        weight_1 = sum(1 for e in edges if e.get("weight", 0) == 1)
        print(f"  • Weight=1 edges: {weight_1}/{len(edges)}")

    if "stats" in data:
        stats = data["stats"]
        print(f"  • Stats sections: {len(stats)}")


def identify_optimizations(main_data, flow_data):
    """Identify specific optimization opportunities."""

    opportunities = []

    # Main data optimizations
    if "data_types" in main_data:
        # Remove empty parameter_types and return_types
        empty_params_count = sum(
            1 for dt in main_data["data_types"] if not dt.get("parameter_types")
        )
        empty_returns_count = sum(
            1 for dt in main_data["data_types"] if not dt.get("return_types")
        )

        if empty_params_count > 0:
            opportunities.append(
                {
                    "type": "remove_empty_lists",
                    "target": "data_types.parameter_types",
                    "count": empty_params_count,
                    "savings": f"{empty_params_count * 20} bytes",
                }
            )

        if empty_returns_count > 0:
            opportunities.append(
                {
                    "type": "remove_empty_lists",
                    "target": "data_types.return_types",
                    "count": empty_returns_count,
                    "savings": f"{empty_returns_count * 20} bytes",
                }
            )

        # Compress function lists
        total_functions = sum(
            len(dt.get("functions", [])) for dt in main_data["data_types"]
        )
        if total_functions > 100:
            opportunities.append(
                {
                    "type": "compress_function_lists",
                    "target": "data_types.functions",
                    "count": total_functions,
                    "savings": f"{total_functions * 10} bytes",
                }
            )

    # Flow graph optimizations
    if "nodes" in flow_data:
        nodes = flow_data["nodes"]

        # Remove empty types
        empty_types = [
            name for name, node in nodes.items() if not node.get("types", [])
        ]
        if len(empty_types) > 100:
            opportunities.append(
                {
                    "type": "remove_empty_types",
                    "target": "nodes.types",
                    "count": len(empty_types),
                    "savings": f"{len(empty_types) * 15} bytes",
                }
            )

        # Remove zero-connection nodes
        zero_conn = [
            name
            for name, node in nodes.items()
            if node.get("in_deg", 0) == 0 and node.get("out_deg", 0) == 0
        ]
        if len(zero_conn) > 50:
            opportunities.append(
                {
                    "type": "remove_zero_connections",
                    "target": "nodes.isolated",
                    "count": len(zero_conn),
                    "savings": f"{len(zero_conn) * 30} bytes",
                }
            )

        # Compress module names
        module_repeats = Counter(
            node.get("module", "").split(".")[0] for node in nodes.values()
        )
        if len(module_repeats) > 10:
            opportunities.append(
                {
                    "type": "compress_module_names",
                    "target": "nodes.module",
                    "count": len(module_repeats),
                    "savings": f"{len(nodes) * 5} bytes",
                }
            )

    if "edges" in flow_data:
        edges = flow_data["edges"]

        # Remove redundant weight=1
        weight_1_edges = [e for e in edges if e.get("weight", 0) == 1]
        if len(weight_1_edges) > len(edges) * 0.8:
            opportunities.append(
                {
                    "type": "remove_default_weights",
                    "target": "edges.weight",
                    "count": len(weight_1_edges),
                    "savings": f"{len(weight_1_edges) * 10} bytes",
                }
            )

    # Print opportunities
    for opp in opportunities:
        print(f"  • {opp['type']}: {opp['count']} items → {opp['savings']}")

    return opportunities


def apply_optimizations(main_data, flow_data, opportunities):
    """Apply identified optimizations."""

    optimized_main = main_data.copy()
    optimized_flow = flow_data.copy()

    # Apply main data optimizations
    if "data_types" in optimized_main:
        for dt in optimized_main["data_types"]:
            # Remove empty lists
            if not dt.get("parameter_types"):
                dt.pop("parameter_types", None)
            if not dt.get("return_types"):
                dt.pop("return_types", None)

            # Compress function lists (show only first 10)
            if len(dt.get("functions", [])) > 10:
                dt["functions"] = dt["functions"][:10] + [
                    f"... and {len(dt['functions']) - 10} more"
                ]

    # Apply flow graph optimizations
    if "nodes" in optimized_flow:
        for node_id, node in optimized_flow["nodes"].items():
            # Remove empty types
            if not node.get("types", []):
                node.pop("types", None)

            # Compress module names
            if "module" in node:
                module_parts = node["module"].split(".")
                if len(module_parts) > 2:
                    node["module"] = f"{module_parts[0]}.{module_parts[1]}..."

    if "edges" in optimized_flow:
        # Remove default weights
        for edge in optimized_flow["edges"]:
            if edge.get("weight", 0) == 1:
                edge.pop("weight", None)

    print("  ✓ Applied all optimizations")
    return optimized_main, optimized_flow


def save_optimized_files(optimized_main, optimized_flow):
    """Save optimized files."""

    # Save optimized main
    main_path = Path("output_structures/data_structures_optimized.yaml")
    with open(main_path, "w") as f:
        yaml.dump(optimized_main, f, default_flow_style=False, sort_keys=False)

    # Save optimized flow
    flow_path = Path("output_structures/data_flow_graph_optimized.yaml")
    with open(flow_path, "w") as f:
        yaml.dump(optimized_flow, f, default_flow_style=False, sort_keys=False)

    print("  ✓ Saved optimized files:")
    print(f"    - {main_path.name}: {main_path.stat().st_size / 1024:.1f}K")
    print(f"    - {flow_path.name}: {flow_path.stat().st_size / 1024:.1f}K")


def show_comparison(original_main, original_flow, optimized_main, optimized_flow):
    """Show before/after comparison."""

    print("\n📊 OPTIMIZATION COMPARISON:")
    print("┌─────────────────────────┬──────────┬──────────┬──────────┐")
    print("│ File                    │ Original │ Optimized │ Reduction │")
    print("├─────────────────────────┼──────────┼──────────┼──────────┤")

    # Main file comparison
    orig_main_size = len(str(original_main).encode())
    opt_main_size = len(str(optimized_main).encode())
    main_reduction = (orig_main_size - opt_main_size) / orig_main_size * 100

    print(
        f"│ Main data               │ {orig_main_size / 1024:8.1f}K │ {opt_main_size / 1024:8.1f}K │ {main_reduction:8.1f}% │"
    )

    # Flow file comparison
    orig_flow_size = len(str(original_flow).encode())
    opt_flow_size = len(str(optimized_flow).encode())
    flow_reduction = (orig_flow_size - opt_flow_size) / orig_flow_size * 100

    print(
        f"│ Flow graph              │ {orig_flow_size / 1024:8.1f}K │ {opt_flow_size / 1024:8.1f}K │ {flow_reduction:8.1f}% │"
    )

    # Total comparison
    total_orig = orig_main_size + orig_flow_size
    total_opt = opt_main_size + opt_flow_size
    total_reduction = (total_orig - total_opt) / total_orig * 100

    print(
        f"│ Total                   │ {total_orig / 1024:8.1f}K │ {total_opt / 1024:8.1f}K │ {total_reduction:8.1f}% │"
    )
    print("└─────────────────────────┴──────────┴──────────┴──────────┘")

    print(
        f"\n🎯 TOTAL SAVINGS: {total_reduction:.1f}% ({(total_orig - total_opt) / 1024:.1f}K)"
    )

    # Additional optimizations possible
    print("\n💡 FURTHER OPTIMIZATIONS POSSIBLE:")
    print("  • Convert to JSON format (~15% smaller)")
    print("  • Use binary formats (MessagePack, ~40% smaller)")
    print("  • Implement compression (gzip, ~70% smaller)")
    print("  • Database storage for large datasets")


if __name__ == "__main__":
    analyze_yaml_optimization()
