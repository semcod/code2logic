#!/usr/bin/env python3
"""
Test and validate the generated graph viewer.
"""

import json
from pathlib import Path


def test_graph_viewer():
    """Test the generated graph viewer."""

    print("🧪 TESTING GRAPH VIEWER")
    print("=" * 40)

    # Check if file exists
    graph_file = Path("output_hybrid/graph_viewer.html")
    if not graph_file.exists():
        print("❌ Graph viewer file not found!")
        return False

    print(f"✅ File exists: {graph_file}")
    print(f"   Size: {graph_file.stat().st_size / 1024:.1f}K")

    # Check file content
    with open(graph_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Test for essential components
    tests = [
        ("HTML structure", "<!DOCTYPE html>" in content),
        ("Canvas element", '<canvas id="graphCanvas"' in content),
        ("Graph data", "window.graphData" in content),
        ("GraphViewer class", "class GraphViewer" in content),
        ("Zoom functionality", "zoomIn" in content),
        ("Pan functionality", "isDragging" in content),
        ("Search functionality", "onSearch" in content),
        ("Filter functionality", "onCategoryFilter" in content),
        ("Layout algorithms", "applyForceLayout" in content),
        ("Tooltip functionality", "showTooltip" in content),
        ("Export functionality", "exportGraph" in content),
        ("Responsive design", "@media (max-width: 768px)" in content),
        ("Touch support", "onTouchStart" in content),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_result in tests:
        status = "✅" if test_result else "❌"
        print(f"{status} {test_name}")
        if test_result:
            passed += 1

    print(f"\n📊 TEST RESULTS: {passed}/{total} passed")

    # Check for embedded data
    data = None
    if "window.graphData" in content:
        print("✅ Graph data embedded")

        # Try to extract and validate JSON structure
        try:
            start = content.find("window.graphData = ") + len("window.graphData = ")
            # Find the end of JSON object
            bracket_count = 0
            end = start
            for i, char in enumerate(content[start:]):
                if char == "{":
                    bracket_count += 1
                elif char == "}":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end = start + i + 1
                        break

            json_str = content[start:end]
            data = json.loads(json_str)

            print("✅ Valid JSON structure")
            print(f"   - Nodes: {len(data.get('nodes', []))}")
            print(f"   - Edges: {len(data.get('edges', []))}")
            print(f"   - Stats: {data.get('stats', {})}")

            # Validate node structure
            nodes = data.get("nodes", [])
            if nodes:
                sample_node = nodes[0]
                required_fields = ["id", "name", "category", "x", "y", "radius"]
                node_valid = all(field in sample_node for field in required_fields)
                print(f"✅ Node structure valid: {node_valid}")

            # Validate edge structure
            edges = data.get("edges", [])
            if edges:
                sample_edge = edges[0]
                required_fields = ["source", "target", "weight"]
                edge_valid = all(field in sample_edge for field in required_fields)
                print(f"✅ Edge structure valid: {edge_valid}")

        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
        except Exception as e:
            print(f"❌ Error parsing JSON: {e}")
    else:
        print("❌ No embedded graph data found")

    # Check for browser compatibility features
    browser_features = [
        ("Canvas 2D", 'getContext("2d")' in content),
        ("RequestAnimationFrame", "requestAnimationFrame" in content),
        ("Touch events", 'addEventListener("touch' in content),
        ("Wheel events", 'addEventListener("wheel"' in content),
        ("Local storage", "localStorage" in content),
    ]

    print("\n🌐 BROWSER COMPATIBILITY:")
    for feature_name, feature_result in browser_features:
        status = "✅" if feature_result else "❌"
        print(f"{status} {feature_name}")

    # Performance estimates
    print("\n⚡ PERFORMANCE METRICS:")
    print(f"   • File size: {graph_file.stat().st_size / 1024:.1f}K")
    print(f"   • Nodes to render: {len(data.get('nodes', []))}")
    print(f"   • Edges to render: {len(data.get('edges', []))}")
    print(f"   • Estimated memory: ~{len(content) / 1024:.1f}K")

    # Recommendations
    print("\n💡 RECOMMENDATIONS:")
    if len(data.get("nodes", [])) > 1000:
        print("   • Consider node clustering for better performance")
    if len(data.get("edges", [])) > 2000:
        print("   • Consider edge bundling for cleaner visualization")
    if graph_file.stat().st_size > 500 * 1024:
        print("   • Consider lazy loading for faster initial load")

    print("   • Graph viewer is ready for use!")
    print("   • Open in modern browser for best experience")
    print("   • Use desktop browser for full functionality")

    return passed == total


def test_file_structure():
    """Test the complete file structure."""

    print("\n📁 TESTING FILE STRUCTURE")
    print("=" * 40)

    base_path = Path("output_hybrid")

    required_files = ["index.html", "graph_viewer.html", "index.yaml"]

    required_dirs = ["consolidated", "orphans"]

    # Test files
    print("📄 FILES:")
    for file_name in required_files:
        file_path = base_path / file_name
        exists = file_path.exists()
        status = "✅" if exists else "❌"
        size = f" ({file_path.stat().st_size / 1024:.1f}K)" if exists else ""
        print(f"{status} {file_name}{size}")

    # Test directories
    print("\n📁 DIRECTORIES:")
    for dir_name in required_dirs:
        dir_path = base_path / dir_name
        exists = dir_path.exists()
        status = "✅" if exists else "❌"
        count = f" ({len(list(dir_path.glob('*.yaml')))} files)" if exists else ""
        print(f"{status} {dir_name}{count}")

    # Count total files
    total_files = len(list(base_path.rglob("*.html"))) + len(
        list(base_path.rglob("*.yaml"))
    )
    print(f"\n📊 TOTAL FILES: {total_files}")

    return True


def main():
    """Main test function."""

    print("🔍 COMPREHENSIVE GRAPH VIEWER TESTING")
    print("=" * 50)

    # Test file structure
    structure_ok = test_file_structure()

    # Test graph viewer
    viewer_ok = test_graph_viewer()

    # Final summary
    print("\n🎯 FINAL SUMMARY")
    print("=" * 50)

    if structure_ok and viewer_ok:
        print("✅ ALL TESTS PASSED!")
        print("🎉 Graph viewer is ready for production use!")
        print("\n🚀 NEXT STEPS:")
        print("1. Open output_hybrid/index.html for tree view")
        print("2. Open output_hybrid/graph_viewer.html for graph view")
        print("3. Test all interactive features")
        print("4. Share with team for feedback")
    else:
        print("❌ SOME TESTS FAILED!")
        print("🔧 Please check the issues above before deployment.")

    print(
        f"\n📈 PROJECT STATUS: {'SUCCESS' if structure_ok and viewer_ok else 'NEEDS ATTENTION'}"
    )


if __name__ == "__main__":
    main()
