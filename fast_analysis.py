#!/usr/bin/env python3
"""
Ultra-fast Python code analysis without external dependencies
"""

import ast
import json
import time
from pathlib import Path
from collections import defaultdict, Counter


class FastAnalyzer:
    def __init__(self, root_path):
        self.root_path = Path(root_path)
        self.calls = defaultdict(set)
        self.imports = defaultdict(set)
        self.classes = {}
        self.functions = {}
        self.modules = set()

    def analyze_file(self, file_path):
        """Analyze single Python file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            module_name = str(file_path.relative_to(self.root_path).with_suffix(""))
            self.modules.add(module_name)

            # Track imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.imports[module_name].add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.imports[module_name].add(node.module)

            # Track functions and calls
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = f"{module_name}.{node.name}"
                    self.functions[func_name] = {
                        "module": module_name,
                        "name": node.name,
                        "line": node.lineno,
                    }

                    # Find calls within this function
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Name):
                                self.calls[func_name].add(child.func.id)
                            elif isinstance(child.func, ast.Attribute):
                                # Handle method calls and qualified names
                                call_parts = []
                                current = child.func
                                while isinstance(current, ast.Attribute):
                                    call_parts.append(current.attr)
                                    current = current.value
                                if isinstance(current, ast.Name):
                                    call_parts.append(current.id)
                                if call_parts:
                                    call_name = ".".join(reversed(call_parts))
                                    self.calls[func_name].add(call_name)

                elif isinstance(node, ast.ClassDef):
                    class_name = f"{module_name}.{node.name}"
                    self.classes[class_name] = {
                        "module": module_name,
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [
                            n.name for n in node.body if isinstance(n, ast.FunctionDef)
                        ],
                    }

        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")

    def analyze_directory(self, max_files=100):
        """Analyze directory with limit"""
        python_files = list(self.root_path.rglob("*.py"))

        # Limit to most important files first
        important_files = []
        for file_path in python_files:
            if "__pycache__" in str(file_path):
                continue
            if "test" in file_path.name.lower():
                continue
            important_files.append(file_path)

        # Take only first N files
        files_to_analyze = important_files[:max_files]

        print(f"Analyzing {len(files_to_analyze)} files...")

        start_time = time.time()
        for i, file_path in enumerate(files_to_analyze):
            if i % 20 == 0:
                print(f"  Progress: {i}/{len(files_to_analyze)}")
            self.analyze_file(file_path)

        end_time = time.time()
        print(f"Analysis completed in {end_time - start_time:.2f}s")

        return {
            "modules": len(self.modules),
            "functions": len(self.functions),
            "classes": len(self.classes),
            "calls": len(self.calls),
            "imports": len(self.imports),
        }

    def generate_mermaid(self, max_nodes=50):
        """Generate limited Mermaid diagram"""
        lines = ["graph TD"]

        # Add most connected functions
        func_connections = Counter()
        for func, calls in self.calls.items():
            func_connections[func] += len(calls)

        top_functions = [f for f, _ in func_connections.most_common(max_nodes)]

        # Add nodes
        for func in top_functions:
            safe_name = func.replace(".", "_").replace("-", "_")
            lines.append(f'    {safe_name}["{func}"]')

        # Add edges (limited)
        edge_count = 0
        max_edges = 100

        for func in top_functions:
            if edge_count >= max_edges:
                break

            safe_func = func.replace(".", "_").replace("-", "_")
            for call in list(self.calls.get(func, []))[:5]:  # Limit calls per function
                if edge_count >= max_edges:
                    break

                safe_call = call.replace(".", "_").replace("-", "_")
                lines.append(f"    {safe_func} --> {safe_call}")
                edge_count += 1

        return "\n".join(lines)

    def generate_report(self):
        """Generate text report"""
        report = []
        report.append("# Fast Code Analysis Report")
        report.append("")
        report.append("## Summary")
        report.append(f"- Modules: {len(self.modules)}")
        report.append(f"- Functions: {len(self.functions)}")
        report.append(f"- Classes: {len(self.classes)}")
        report.append(f"- Function calls: {len(self.calls)}")
        report.append("")

        # Top modules by function count
        module_functions = defaultdict(int)
        for func_name, func_info in self.functions.items():
            module_functions[func_info["module"]] += 1

        report.append("## Top Modules")
        for module, count in sorted(
            module_functions.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            report.append(f"- {module}: {count} functions")
        report.append("")

        # Most called functions
        call_frequency = Counter()
        for calls in self.calls.values():
            for call in calls:
                call_frequency[call] += 1

        report.append("## Most Called Functions")
        for func, count in call_frequency.most_common(20):
            report.append(f"- {func}: {count} calls")
        report.append("")

        # Classes with most methods
        report.append("## Classes by Method Count")
        class_methods = {
            name: len(info["methods"]) for name, info in self.classes.items()
        }
        for class_name, method_count in sorted(
            class_methods.items(), key=lambda x: x[1], reverse=True
        )[:15]:
            report.append(f"- {class_name}: {method_count} methods")

        return "\n".join(report)


def main():
    print("🚀 Ultra-Fast Python Code Analysis")
    print("===================================")

    # Analyze nlp2cmd
    analyzer = FastAnalyzer("../src/nlp2cmd")

    # Quick analysis with limits
    stats = analyzer.analyze_directory(max_files=50)  # Limit to 50 files for speed

    print("\n📊 Analysis Results:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Generate outputs
    print("\n📝 Generating reports...")

    # Text report
    report = analyzer.generate_report()
    with open("./output_fast/fast_analysis_report.md", "w") as f:
        f.write(report)

    # Mermaid diagram (limited)
    mermaid = analyzer.generate_mermaid(max_nodes=30)
    with open("./output_fast/calls_fast.mmd", "w") as f:
        f.write(mermaid)

    # JSON data
    data = {
        "stats": stats,
        "functions": dict(analyzer.functions),
        "classes": dict(analyzer.classes),
        "calls": {k: list(v) for k, v in analyzer.calls.items()},
        "imports": {k: list(v) for k, v in analyzer.imports.items()},
    }

    with open("./output_fast/analysis_data.json", "w") as f:
        json.dump(data, f, indent=2)

    print("✅ Analysis complete!")
    print("📁 Outputs created:")
    print("  - ./output_fast/fast_analysis_report.md")
    print("  - ./output_fast/calls_fast.mmd")
    print("  - ./output_fast/analysis_data.json")


if __name__ == "__main__":
    main()
