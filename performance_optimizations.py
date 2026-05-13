#!/usr/bin/env python3
"""
Performance optimizations for code2flow on large projects
"""

import subprocess
import time
from pathlib import Path


def run_optimized_analysis():
    """Run code2flow with performance optimizations"""

    print("🚀 Running optimized code2flow analysis...")

    # 1. Use faster layout algorithm
    print("\n1️⃣ Using fast layout algorithms...")

    cmd_fast = [
        "code2flow",
        "../src/nlp2cmd/",
        "-v",
        "-o",
        "./output_fast",
        "--layout",
        "sfdp",  # Much faster than spring
        "--max-depth",
        "3",  # Limit depth
        "--filter",
        "exclude_tests",  # Exclude test files
    ]

    try:
        start_time = time.time()
        result = subprocess.run(cmd_fast, capture_output=True, text=True, timeout=300)
        end_time = time.time()

        print(f"✅ Fast analysis completed in {end_time - start_time:.1f}s")
        if result.stdout:
            print("STDOUT:", result.stdout[:500])
        if result.stderr:
            print("STDERR:", result.stderr[:500])

    except subprocess.TimeoutExpired:
        print("❌ Fast analysis timed out")
    except Exception as e:
        print(f"❌ Fast analysis failed: {e}")

    # 2. Chunked analysis for very large projects
    print("\n2️⃣ Running chunked analysis...")

    src_path = Path("../src/nlp2cmd")
    if src_path.exists():
        # Analyze major modules separately
        modules = [
            "adapters",
            "automation",
            "llm",
            "generation",
            "pipeline_runner",
            "web_schema",
        ]

        for i, module in enumerate(modules):
            module_path = src_path / module
            if module_path.exists():
                print(f"   📦 Analyzing module {i + 1}/{len(modules)}: {module}")

                cmd_chunk = [
                    "code2flow",
                    str(module_path),
                    "-v",
                    "-o",
                    f"./output_chunk_{module}",
                    "--layout",
                    "dot",  # Fastest layout
                    "--max-depth",
                    "2",
                ]

                try:
                    start = time.time()
                    result = subprocess.run(
                        cmd_chunk, capture_output=True, text=True, timeout=60
                    )
                    end = time.time()
                    print(f"      ✅ {module} completed in {end - start:.1f}s")

                except subprocess.TimeoutExpired:
                    print(f"      ⏰ {module} timed out")
                except Exception as e:
                    print(f"      ❌ {module} failed: {e}")

    # 3. Generate optimized Mermaid with higher edge limits
    print("\n3️⃣ Generating Mermaid with custom configuration...")

    mermaid_config = """
{
  "maxEdges": 5000,
  "flowchart": {
    "htmlLabels": true,
    "curve": "basis"
  }
}
"""

    config_path = Path("./output/mermaid_config.json")
    config_path.write_text(mermaid_config)

    # Use custom mermaid-cli with higher limits
    cmd_mermaid = [
        "npx",
        "@mermaid-js/mermaid-cli",
        "-i",
        "./output/flow.mmd",
        "-o",
        "./output/flow_high_limit.png",
        "--config",
        str(config_path),
        "--backgroundColor",
        "transparent",
    ]

    try:
        print("   🎨 Rendering with high edge limit...")
        result = subprocess.run(
            cmd_mermaid, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print("   ✅ High-limit Mermaid render successful")
        else:
            print("   ⚠️ Mermaid render issues (check logs)")
    except Exception as e:
        print(f"   ❌ Mermaid render failed: {e}")


def create_performance_script():
    """Create a performance optimization script"""

    script_content = """#!/bin/bash
# Fast code2flow analysis for large projects

echo "🚀 Fast Code2Flow Analysis"
echo "=========================="

# Set environment variables for performance
export OMP_NUM_THREADS=4
export NUMBA_NUM_THREADS=4
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Fast analysis with optimizations
echo "1️⃣ Quick analysis (spring layout, limited depth)"
time code2flow ../src/nlp2cmd/ \\
    -v \\
    -o ./output_quick \\
    --layout spring \\
    --max-depth 2 \\
    --max-nodes 1000 \\
    --exclude "*test*" \\
    --exclude "*__pycache__*"

echo ""
echo "2️⃣ Ultra-fast analysis (dot layout, minimal depth)"
time code2flow ../src/nlp2cmd/ \\
    -v \\
    -o ./output_ultra \\
    --layout dot \\
    --max-depth 1 \\
    --max-nodes 500

echo ""
echo "3️⃣ Module-by-module analysis"
for module in adapters automation llm generation pipeline_runner web_schema; do
    if [ -d "../src/nlp2cmd/$module" ]; then
        echo "📦 Analyzing $module..."
        time code2flow "../src/nlp2cmd/$module" \\
            -v \\
            -o "./output_modules/$module" \\
            --layout dot \\
            --max-depth 2
    fi
done

echo ""
echo "✅ Analysis complete!"
echo "Check output directories:"
echo "  - ./output_quick/"
echo "  - ./output_ultra/" 
echo "  - ./output_modules/"
"""

    script_path = Path("./fast_analysis.sh")
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    print(f"📜 Created fast analysis script: {script_path}")


def suggest_alternatives():
    """Suggest alternative faster tools"""

    alternatives = """
🔥 Alternative Fast Analysis Tools:
==================================

1. **pyan3** - Fast Python call graph generator
   pip install pyan3
   pyan3 ../src/nlp2cmd/ --uses --defines --dot > output_pyan3.dot

2. **snakefood** - Very fast dependency analysis  
   pip install snakefood
   sfood-graph ../src/nlp2cmd/ | dot -Tpng -o output_snakefood.png

3. **pydeps** - Quick dependency visualization
   pip install pydeps
   pydeps ../src/nlp2cmd/ --show-deps --max-bacon=2 -o output_pydeps.png

4. **Custom NetworkX optimization**:
   - Use 'dot' or 'sfdp' layout instead of 'spring'
   - Limit graph to top-level functions only
   - Remove isolated nodes
   - Use graph clustering for large projects

5. **Graphviz-only approach**:
   # Generate DOT file directly
   find ../src/nlp2cmd/ -name "*.py" | xargs python -c "
import ast, sys
for file in sys.argv[1:]:
    try:
        with open(file) as f: tree = ast.parse(f.read())
        # Extract call relationships...
    except: pass
" > calls.dot
   
   # Render with Graphviz
   dot -Tpng -Ksfdp calls.dot -o calls.png
"""

    print(alternatives)


if __name__ == "__main__":
    print("🎯 Code2Flow Performance Optimization")
    print("====================================")

    # Create performance script
    create_performance_script()

    # Run optimized analysis
    run_optimized_analysis()

    # Show alternatives
    suggest_alternatives()

    print("\n🏁 Performance optimization complete!")
