#!/usr/bin/env python3
"""
Split and optimize data structures YAML file.

Separates data_flow_graph into its own file and optimizes node format.
"""

import yaml
from pathlib import Path


def split_and_optimize_yaml():
    """Split data_structures_v2.yaml into optimized files."""

    # Load the original file
    input_path = Path("output_structures/data_structures_v2.yaml")
    with open(input_path, "r") as f:
        data = yaml.safe_load(f)

    # Extract data_flow_graph
    data_flow_graph = data.pop("data_flow_graph", None)

    # Optimize nodes format
    if data_flow_graph and "nodes" in data_flow_graph:
        optimized_nodes = {}
        for node_id, node_data in data_flow_graph["nodes"].items():
            # Simplified node format
            optimized_nodes[node_id] = {
                "name": node_data["name"],
                "module": node_data["module"],
                "in_deg": node_data["in_degree"],
                "out_deg": node_data["out_degree"],
                "hub": node_data["is_hub"],
                "types": node_data["data_types"],
            }

        data_flow_graph["nodes"] = optimized_nodes

    # Save main data structures (without data_flow_graph)
    main_output_path = Path("output_structures/data_structures_main.yaml")
    with open(main_output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    # Save data flow graph separately
    if data_flow_graph:
        flow_output_path = Path("output_structures/data_flow_graph.yaml")
        with open(flow_output_path, "w") as f:
            yaml.dump(data_flow_graph, f, default_flow_style=False, sort_keys=False)

    print("✓ Split complete!")
    print(f"  - Main data: {main_output_path}")
    print(f"  - Flow graph: {flow_output_path}")

    # Show optimization results
    if data_flow_graph and "nodes" in data_flow_graph:
        print(f"  - Nodes optimized: {len(data_flow_graph['nodes'])}")
        print("  - Original format: verbose")
        print("  - New format: compact")

    return main_output_path, flow_output_path


if __name__ == "__main__":
    split_and_optimize_yaml()
