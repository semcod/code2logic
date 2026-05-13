#!/usr/bin/env python3
"""
Ultimate YAML optimization with advanced techniques.

Implements multiple optimization strategies for maximum compression.
"""

import yaml
import json
import gzip
import pickle
from pathlib import Path
import msgpack


def ultimate_yaml_optimization():
    """Apply ultimate optimization techniques."""

    print("🚀 ULTIMATE YAML OPTIMIZATION")
    print("=" * 50)

    # Load current optimized files
    main_path = Path("output_structures/data_structures_optimized.yaml")
    flow_path = Path("output_structures/data_flow_graph_optimized.yaml")

    with open(main_path, "r") as f:
        main_data = yaml.safe_load(f)

    with open(flow_path, "r") as f:
        flow_data = yaml.safe_load(f)

    original_size = main_path.stat().st_size + flow_path.stat().st_size
    print(f"📁 Current optimized size: {original_size / 1024:.1f}K")

    # Apply aggressive optimizations
    print("\n⚡ APPLYING AGGRESSIVE OPTIMIZATIONS:")

    # 1. Remove all redundant data
    ultra_main = ultra_compress_main(main_data)
    ultra_flow = ultra_compress_flow(flow_data)

    # 2. Create multiple format versions
    formats = create_all_formats(ultra_main, ultra_flow)

    # 3. Show comparison
    show_ultimate_comparison(original_size, formats)

    # 4. Generate recommendations
    generate_recommendations(formats)


def ultra_compress_main(data):
    """Ultra-compress main data structure."""

    compressed = {
        "path": data.get("project_path", ""),
        "type": data.get("analysis_type", ""),
        "summary": data.get("summary", {}),
    }

    # Compress data_types - keep only essential info
    if "data_types" in data:
        compressed["types"] = []
        for dt in data["data_types"][:20]:  # Keep only top 20
            compressed["types"].append(
                {
                    "name": dt.get("type_name", ""),
                    "usage": dt.get("usage_count", 0),
                    "cross": dt.get("cross_module_usage", 0),
                }
            )

    # Compress process_patterns
    if "process_patterns" in data:
        compressed["patterns"] = []
        for pattern in data["process_patterns"]:
            compressed["patterns"].append(
                {
                    "type": pattern.get("pattern_type", ""),
                    "count": pattern.get("count", 0),
                }
            )

    # Compress optimization_analysis
    if "optimization_analysis" in data:
        opt = data["optimization_analysis"]
        compressed["opt"] = {
            "score": opt.get("potential_score", 0),
            "recs": len(opt.get("recommendations", [])),
        }

    print("  ✓ Ultra-compressed main data")
    return compressed


def ultra_compress_flow(data):
    """Ultra-compress flow graph."""

    compressed = {"nodes": {}, "stats": {}}

    # Keep only hub nodes and top connections
    if "nodes" in data:
        for node_id, node in data["nodes"].items():
            # Keep only hubs or high-connection nodes
            if (
                node.get("hub", False)
                or node.get("in_deg", 0) + node.get("out_deg", 0) > 10
            ):
                compressed["nodes"][node_id] = {
                    "in": node.get("in_deg", 0),
                    "out": node.get("out_deg", 0),
                    "hub": node.get("hub", False),
                }

    # Keep essential stats
    if "stats" in data:
        stats = data["stats"]
        compressed["stats"] = {
            "nodes": stats.get("total_nodes", 0),
            "edges": stats.get("total_edges", 0),
            "hubs": stats.get("hub_nodes", 0),
        }

    print("  ✓ Ultra-compressed flow graph")
    return compressed


def create_all_formats(main_data, flow_data):
    """Create multiple format versions."""

    formats = {}
    combined = {"main": main_data, "flow": flow_data}

    # YAML (current)
    yaml_main = yaml.dump(main_data, default_flow_style=False, sort_keys=False)
    yaml_flow = yaml.dump(flow_data, default_flow_style=False, sort_keys=False)
    yaml_size = len(yaml_main.encode()) + len(yaml_flow.encode())
    formats["yaml"] = {"size": yaml_size, "data": (yaml_main, yaml_flow)}

    # JSON
    json_main = json.dumps(main_data, separators=(",", ":"))
    json_flow = json.dumps(flow_data, separators=(",", ":"))
    json_size = len(json_main.encode()) + len(json_flow.encode())
    formats["json"] = {"size": json_size, "data": (json_main, json_flow)}

    # MessagePack
    msgpack_main = msgpack.packb(main_data)
    msgpack_flow = msgpack.packb(flow_data)
    msgpack_size = len(msgpack_main) + len(msgpack_flow)
    formats["msgpack"] = {"size": msgpack_size, "data": (msgpack_main, msgpack_flow)}

    # Pickle
    pickle_main = pickle.dumps(main_data)
    pickle_flow = pickle.dumps(flow_data)
    pickle_size = len(pickle_main) + len(pickle_flow)
    formats["pickle"] = {"size": pickle_size, "data": (pickle_main, pickle_flow)}

    # GZIP compressed JSON
    gzip_json_main = gzip.compress(json_main.encode())
    gzip_json_flow = gzip.compress(json_flow.encode())
    gzip_json_size = len(gzip_json_main) + len(gzip_json_flow)
    formats["gzip_json"] = {
        "size": gzip_json_size,
        "data": (gzip_json_main, gzip_json_flow),
    }

    # GZIP compressed MessagePack
    gzip_msgpack_main = gzip.compress(msgpack_main)
    gzip_msgpack_flow = gzip.compress(msgpack_flow)
    gzip_msgpack_size = len(gzip_msgpack_main) + len(gzip_msgpack_flow)
    formats["gzip_msgpack"] = {
        "size": gzip_msgpack_size,
        "data": (gzip_msgpack_main, gzip_msgpack_flow),
    }

    # Save all formats
    save_all_formats(formats)

    return formats


def save_all_formats(formats):
    """Save all format versions."""

    base_path = Path("output_structures/ultimate")
    base_path.mkdir(exist_ok=True)

    for format_name, format_data in formats.items():
        if format_name == "yaml":
            main_content, flow_content = format_data["data"]
            with open(base_path / f"data_structures_{format_name}.yaml", "w") as f:
                f.write(main_content)
            with open(base_path / f"data_flow_graph_{format_name}.yaml", "w") as f:
                f.write(flow_content)

        elif format_name == "json":
            main_content, flow_content = format_data["data"]
            with open(base_path / f"data_structures_{format_name}.json", "w") as f:
                f.write(main_content)
            with open(base_path / f"data_flow_graph_{format_name}.json", "w") as f:
                f.write(flow_content)

        elif format_name in ["msgpack", "pickle"]:
            main_content, flow_content = format_data["data"]
            with open(base_path / f"data_structures_{format_name}.mp", "wb") as f:
                f.write(main_content)
            with open(base_path / f"data_flow_graph_{format_name}.mp", "wb") as f:
                f.write(flow_content)

        elif format_name in ["gzip_json", "gzip_msgpack"]:
            main_content, flow_content = format_data["data"]
            with open(base_path / f"data_structures_{format_name}.gz", "wb") as f:
                f.write(main_content)
            with open(base_path / f"data_flow_graph_{format_name}.gz", "wb") as f:
                f.write(flow_content)

        print(f"  ✓ Saved {format_name}: {format_data['size'] / 1024:.1f}K")


def show_ultimate_comparison(original_size, formats):
    """Show ultimate comparison table."""

    print("\n📊 ULTIMATE OPTIMIZATION COMPARISON:")
    print("┌─────────────────────┬──────────┬──────────┬──────────┐")
    print("│ Format              │ Size     │ Reduction │ Savings  │")
    print("├─────────────────────┼──────────┼──────────┼──────────┤")

    for format_name, format_data in formats.items():
        size = format_data["size"]
        reduction = (original_size - size) / original_size * 100
        savings = original_size - size

        print(
            f"│ {format_name:19} │ {size / 1024:8.1f}K │ {reduction:8.1f}% │ {savings / 1024:8.1f}K │"
        )

    print("└─────────────────────┴──────────┴──────────┴──────────┘")

    # Find best format
    best_format = min(formats.items(), key=lambda x: x[1]["size"])
    best_reduction = (original_size - best_format[1]["size"]) / original_size * 100

    print(f"\n🏆 BEST FORMAT: {best_format[0]}")
    print(f"   Size: {best_format[1]['size'] / 1024:.1f}K")
    print(f"   Reduction: {best_reduction:.1f}%")
    print(f"   Savings: {(original_size - best_format[1]['size']) / 1024:.1f}K")


def generate_recommendations(formats):
    """Generate usage recommendations."""

    print("\n💡 USAGE RECOMMENDATIONS:")

    recommendations = [
        ("YAML", "Human-readable, debugging", "Development"),
        ("JSON", "Web APIs, JavaScript", "Frontend"),
        ("MessagePack", "Fast binary, efficient", "Production"),
        ("GZIP + JSON", "Maximum compression", "Storage/Transfer"),
        ("GZIP + MessagePack", "Best of both worlds", "Optimal Production"),
    ]

    for format_name, use_case, scenario in recommendations:
        if format_name in formats:
            size = formats[format_name]["size"]
            print(f"  • {format_name:15} - {use_case:25} -> {scenario}")
            print(f"    Size: {size / 1024:.1f}K")

    print("\n🎯 RECOMMENDATION:")
    print("  Use 'gzip_msgpack' for production deployment")
    print("  Use 'yaml' for development and debugging")
    print("  Use 'json' for web API integration")


if __name__ == "__main__":
    ultimate_yaml_optimization()
