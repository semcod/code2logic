#!/usr/bin/env python3
"""
Advanced Flow Analyzer - combines static and dynamic analysis
for comprehensive system behavior understanding and reverse engineering.
"""

import ast
import os
import json
import sys
import time
import subprocess
from collections import defaultdict
from typing import Any, Dict, List, Set, Optional
from dataclasses import dataclass, asdict
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as patches


# =====================================================
# Configuration
# =====================================================

MAX_PATHS_PER_FUNCTION = 20
MAX_DEPTH_ENUMERATION = 10
MAX_DEPTH_INTERPROCEDURAL = 3
MAX_TOTAL_PATHS = 1000

# Analysis modes
MODES = {
    "static": "Static AST-based analysis",
    "dynamic": "Runtime execution tracing",
    "hybrid": "Combined static + dynamic analysis",
    "behavioral": "Behavioral pattern extraction",
    "reverse": "Reverse engineering ready output",
}


# =====================================================
# Data Structures
# =====================================================


@dataclass
class FlowNode:
    """Represents a node in the control flow graph."""

    id: int
    type: str  # FUNC, CALL, IF, ASSIGN, etc.
    label: str
    function: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    conditions: List[str] = None
    data_flow: List[str] = None

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = []
        if self.data_flow is None:
            self.data_flow = []


@dataclass
class ExecutionTrace:
    """Runtime execution trace for dynamic analysis."""

    function: str
    entry_time: float
    exit_time: Optional[float] = None
    args: List[Any] = None
    return_value: Any = None
    calls_made: List[str] = None
    exceptions: List[str] = None

    def __post_init__(self):
        if self.args is None:
            self.args = []
        if self.calls_made is None:
            self.calls_made = []
        if self.exceptions is None:
            self.exceptions = []


@dataclass
class BehavioralPattern:
    """Extracted behavioral pattern from code analysis."""

    name: str
    type: str  # sequential, conditional, iterative, recursive, state_machine
    entry_points: List[str]
    exit_points: List[str]
    decision_points: List[str]
    data_transformations: Dict[str, str]
    frequency: int
    confidence: float


# =====================================================
# Enhanced Static Analyzer
# =====================================================


class EnhancedFlowExtractor(ast.NodeVisitor):
    """Enhanced AST visitor with data flow and behavior analysis."""

    def __init__(self, module_name: str, file_path: str):
        self.module = module_name
        self.file_path = file_path

        # Graph structures
        self.cfg = defaultdict(list)  # Control Flow Graph
        self.dfg = defaultdict(list)  # Data Flow Graph
        self.call_graph = defaultdict(set)

        # Node tracking
        self.nodes = {}
        self.node_id = 0
        self.current_node = None

        # Context tracking
        self.function_stack = []
        self.class_stack = []
        self.loop_stack = []
        self.variable_scope = defaultdict(list)
        self.data_dependencies = defaultdict(set)

        # Pattern detection
        self.patterns = []
        self.state_machines = []

        # Imports
        self.imports = {}

        # Function entries tracking
        self.function_entries = {}

    def new_node(self, node_type: str, label: str, **kwargs) -> int:
        """Create a new flow node."""
        node_id = self.node_id
        self.node_id += 1

        node = FlowNode(
            id=node_id,
            type=node_type,
            label=label,
            function=self.function_stack[-1] if self.function_stack else None,
            file=self.file_path,
            line=kwargs.get("line"),
            conditions=kwargs.get("conditions", []),
            data_flow=kwargs.get("data_flow", []),
        )

        self.nodes[node_id] = node
        return node_id

    def connect(self, a: Optional[int], b: Optional[int]):
        """Connect two nodes in the CFG."""
        if a is not None and b is not None:
            self.cfg[a].append(b)

    def fq_name(self, name: str) -> str:
        """Get fully qualified name."""
        parts = []
        if self.class_stack:
            parts.append(self.class_stack[-1])
        parts.append(name)
        return f"{self.module}." + ".".join(parts)

    # =================================================
    # Import handling
    # =================================================

    def visit_Import(self, node: ast.Import):
        for n in node.names:
            asname = n.asname or n.name
            self.imports[asname] = n.name

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            for n in node.names:
                asname = n.asname or n.name
                self.imports[asname] = node.module + "." + n.name

    # =================================================
    # Class and function definitions
    # =================================================

    def visit_ClassDef(self, node: ast.ClassDef):
        self.class_stack.append(node.name)

        # Detect state machine pattern
        if self._is_state_machine(node):
            self.state_machines.append(
                {
                    "name": node.name,
                    "states": self._extract_states(node),
                    "transitions": self._extract_transitions(node),
                }
            )

        for stmt in node.body:
            self.visit(stmt)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Enter function context
        self.function_stack.append(self.fq_name(node.name))

        # Create entry node
        entry = self.new_node(
            "FUNC", f"FUNC:{self.fq_name(node.name)}", line=node.lineno
        )
        self.function_entries[self.fq_name(node.name)] = entry

        prev_node = self.current_node
        self.current_node = entry

        # Track variables in this function
        var_scope = f"{self.fq_name(node.name)}_vars"

        # Analyze function body
        for stmt in node.body:
            self._analyze_statement(stmt, var_scope)
            self.visit(stmt)

        # Create exit node
        exit_node = self.new_node(
            "RETURN", f"RETURN:{self.fq_name(node.name)}", line=node.end_lineno
        )
        self.connect(self.current_node, exit_node)

        # Exit function context
        self.function_stack.pop()
        self.current_node = prev_node

    # =================================================
    # Statement analysis with data flow
    # =================================================

    def _analyze_statement(self, stmt: ast.stmt, var_scope: str):
        """Analyze statement for data flow patterns."""

        if isinstance(stmt, ast.Assign):
            # Track variable assignments
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    self.variable_scope[var_scope].append(target.id)

                    # Track data dependencies
                    deps = self._extract_dependencies(stmt.value)
                    self.data_dependencies[target.id].update(deps)

        elif isinstance(stmt, ast.If):
            # Extract condition
            condition = self._extract_condition(stmt.test)
            cond_node = self.new_node(
                "IF", condition, conditions=[condition], line=stmt.lineno
            )
            self.connect(self.current_node, cond_node)

            # Analyze branches
            prev = self.current_node
            self.current_node = cond_node

            for branch_stmt in stmt.body:
                self._analyze_statement(branch_stmt, var_scope)

            for branch_stmt in stmt.orelse:
                self._analyze_statement(branch_stmt, var_scope)

            self.current_node = prev

        elif isinstance(stmt, ast.Call):
            # Track function calls
            call_name = self._resolve_call_name(stmt.func)
            if call_name and self.function_stack:
                self.call_graph[self.function_stack[-1]].add(call_name)

    def _extract_dependencies(self, node: ast.AST) -> Set[str]:
        """Extract variable dependencies from AST node."""
        deps = set()

        if isinstance(node, ast.Name):
            deps.add(node.id)
        elif isinstance(node, ast.BinOp):
            deps.update(self._extract_dependencies(node.left))
            deps.update(self._extract_dependencies(node.right))
        elif isinstance(node, ast.Call):
            for arg in node.args:
                deps.update(self._extract_dependencies(arg))

        return deps

    def _extract_condition(self, node: ast.AST) -> str:
        """Extract string representation of condition."""
        if isinstance(node, ast.Compare):
            left = ast.unparse(node.left) if hasattr(ast, "unparse") else str(node.left)
            ops = [type(op).__name__ for op in node.ops]
            comparators = [
                ast.unparse(c) if hasattr(ast, "unparse") else str(c)
                for c in node.comparators
            ]
            return f"{left} {' '.join(ops)} {' '.join(comparators)}"
        return ast.unparse(node) if hasattr(ast, "unparse") else str(node)

    # =================================================
    # Pattern detection
    # =================================================

    def _is_state_machine(self, node: ast.ClassDef) -> bool:
        """Detect if class implements state machine pattern."""
        # Look for state variables and transition methods
        has_states = any(
            "state" in n.lower()
            for n in [attr.name for attr in node.body if isinstance(attr, ast.Assign)]
        )
        has_transitions = any(
            "transition" in n.lower() or "change" in n.lower()
            for n in [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
        )
        return has_states or has_transitions

    def _extract_states(self, node: ast.ClassDef) -> List[str]:
        """Extract state names from state machine class."""
        states = []
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and "state" in target.id.lower():
                        if isinstance(item.value, ast.Str):
                            states.append(item.value.s)
                        elif isinstance(item.value, ast.List):
                            for elt in item.value.elts:
                                if isinstance(elt, ast.Str):
                                    states.append(elt.s)
        return states

    def _extract_transitions(self, node: ast.ClassDef) -> List[Dict]:
        """Extract state transitions from state machine class."""
        transitions = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if "transition" in item.name.lower() or "change" in item.name.lower():
                    # Analyze transition logic
                    transitions.append(
                        {
                            "method": item.name,
                            "from_state": self._extract_from_state(item),
                            "to_state": self._extract_to_state(item),
                        }
                    )
        return transitions

    def _extract_from_state(self, node: ast.FunctionDef) -> Optional[str]:
        """Extract source state from transition method."""
        # Look for state checks in method body
        for stmt in node.body:
            if isinstance(stmt, ast.If):
                # Simple heuristic: look for self.state == 'something'
                if isinstance(stmt.test, ast.Compare):
                    left = stmt.test.left
                    if isinstance(left, ast.Attribute) and left.attr == "state":
                        if isinstance(stmt.test.comparators[0], ast.Str):
                            return stmt.test.comparators[0].s
        return None

    def _extract_to_state(self, node: ast.FunctionDef) -> Optional[str]:
        """Extract destination state from transition method."""
        # Look for state assignments in method body
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "state":
                        if isinstance(stmt.value, ast.Str):
                            return stmt.value.s
        return None

    # =================================================
    # Call resolution
    # =================================================

    def _resolve_call_name(self, node: ast.AST) -> Optional[str]:
        """Resolve function call name."""
        if isinstance(node, ast.Name):
            name = node.id
            if name in self.imports:
                return self.imports[name]
            return self.module + "." + name

        elif isinstance(node, ast.Attribute):
            parts = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value

            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                parts.reverse()

                root = parts[0]
                if root in self.imports:
                    return self.imports[root] + "." + ".".join(parts[1:])

                return self.module + "." + ".".join(parts)

        return None


# =====================================================
# Dynamic Analyzer
# =====================================================


class DynamicTracer:
    """Runtime execution tracer for dynamic analysis."""

    def __init__(self):
        self.traces = []
        self.call_stack = []
        self.start_time = time.time()
        self.tracing = False
        self.original_trace = None

    def start_tracing(self):
        """Start dynamic tracing."""
        self.tracing = True
        self.original_trace = sys.gettrace()
        sys.settrace(self._trace_function)

    def stop_tracing(self):
        """Stop dynamic tracing."""
        self.tracing = False
        sys.settrace(self.original_trace)

    def _trace_function(self, frame, event, arg):
        """Trace function for sys.settrace."""
        if not self.tracing:
            return None

        filename = frame.f_code.co_filename
        function_name = frame.f_code.co_name

        # Skip external libraries
        if "site-packages" in filename or "dist-packages" in filename:
            return None

        if event == "call":
            trace = ExecutionTrace(
                function=f"{filename}:{function_name}",
                entry_time=time.time() - self.start_time,
            )
            self.traces.append(trace)
            self.call_stack.append(trace)

        elif event == "return":
            if self.call_stack:
                trace = self.call_stack.pop()
                trace.exit_time = time.time() - self.start_time
                trace.return_value = arg

        return self._trace_function

    def get_execution_graph(self) -> nx.DiGraph:
        """Build execution graph from traces."""
        G = nx.DiGraph()

        for trace in self.traces:
            node_id = f"{trace.function}_{trace.entry_time}"
            G.add_node(
                node_id,
                function=trace.function,
                entry_time=trace.entry_time,
                exit_time=trace.exit_time,
            )

            # Add call edges
            if self.call_stack:
                parent = self.call_stack[-1]
                parent_id = f"{parent.function}_{parent.entry_time}"
                G.add_edge(parent_id, node_id)

        return G


# =====================================================
# Behavioral Pattern Extractor
# =====================================================


class BehavioralPatternExtractor:
    """Extract behavioral patterns from combined analysis."""

    def __init__(self, static_analyzer, dynamic_tracer=None):
        self.static = static_analyzer
        self.dynamic = dynamic_tracer
        self.patterns = []

    def extract_patterns(self) -> List[BehavioralPattern]:
        """Extract all behavioral patterns."""
        patterns = []

        # Sequential patterns
        patterns.extend(self._find_sequential_patterns())

        # Conditional patterns
        patterns.extend(self._find_conditional_patterns())

        # Iterative patterns
        patterns.extend(self._find_iterative_patterns())

        # Recursive patterns
        patterns.extend(self._find_recursive_patterns())

        # State machine patterns
        patterns.extend(self._find_state_machine_patterns())

        self.patterns = patterns
        return patterns

    def _find_sequential_patterns(self) -> List[BehavioralPattern]:
        """Find sequential execution patterns."""
        patterns = []

        for fn, entry in self.static.function_entries.items():
            # Look for linear execution chains
            paths = self._enumerate_linear_paths(entry)

            if len(paths) > 0:
                pattern = BehavioralPattern(
                    name=f"sequential_{fn}",
                    type="sequential",
                    entry_points=[fn],
                    exit_points=[],
                    decision_points=[],
                    data_transformations={},
                    frequency=len(paths),
                    confidence=0.8,
                )
                patterns.append(pattern)

        return patterns

    def _find_conditional_patterns(self) -> List[BehavioralPattern]:
        """Find conditional branching patterns."""
        patterns = []

        # Count decision nodes
        decision_nodes = [n for n in self.static.nodes.values() if n.type == "IF"]

        if decision_nodes:
            pattern = BehavioralPattern(
                name="conditional_branching",
                type="conditional",
                entry_points=[],
                exit_points=[],
                decision_points=[n.label for n in decision_nodes],
                data_transformations={},
                frequency=len(decision_nodes),
                confidence=0.9,
            )
            patterns.append(pattern)

        return patterns

    def _find_iterative_patterns(self) -> List[BehavioralPattern]:
        """Find iterative/loop patterns."""
        patterns = []

        # This would need loop detection in the static analyzer
        # For now, return empty list
        return patterns

    def _find_recursive_patterns(self) -> List[BehavioralPattern]:
        """Find recursive function patterns."""
        patterns = []

        # Detect recursion in call graph
        for fn, callees in self.static.call_graph.items():
            if fn in callees:
                pattern = BehavioralPattern(
                    name=f"recursive_{fn}",
                    type="recursive",
                    entry_points=[fn],
                    exit_points=[fn],
                    decision_points=[],
                    data_transformations={},
                    frequency=1,
                    confidence=1.0,
                )
                patterns.append(pattern)

        return patterns

    def _find_state_machine_patterns(self) -> List[BehavioralPattern]:
        """Find state machine patterns."""
        patterns = []

        for sm in self.static.state_machines:
            pattern = BehavioralPattern(
                name=f"state_machine_{sm['name']}",
                type="state_machine",
                entry_points=sm["states"],
                exit_points=[],
                decision_points=[t["method"] for t in sm["transitions"]],
                data_transformations={},
                frequency=len(sm["transitions"]),
                confidence=0.9,
            )
            patterns.append(pattern)

        return patterns

    def _enumerate_linear_paths(
        self, start: int, max_depth: int = 10
    ) -> List[List[int]]:
        """Enumerate linear paths from start node."""
        paths = []

        def dfs(node, path, depth):
            if depth > max_depth:
                return

            path.append(node)

            if node not in self.static.cfg or not self.static.cfg[node]:
                paths.append(path.copy())
            else:
                for nxt in self.static.cfg[node]:
                    dfs(nxt, path, depth + 1)

            path.pop()

        dfs(start, [], 0)
        return paths


# =====================================================
# Reverse Engineering Output Generator
# =====================================================


class ReverseEngineeringGenerator:
    """Generate reverse engineering ready outputs."""

    def __init__(self, analyzer, patterns):
        self.analyzer = analyzer
        self.patterns = patterns

    def generate_llm_prompt(self) -> str:
        """Generate comprehensive LLM prompt for system understanding."""
        prompt = []

        prompt.append("# System Behavioral Analysis\n")
        prompt.append("## Overview\n")
        prompt.append(f"- Total functions: {len(self.analyzer.function_entries)}\n")
        prompt.append(
            f"- Total call graph edges: {sum(len(v) for v in self.analyzer.call_graph.values())}\n"
        )
        prompt.append(f"- Behavioral patterns detected: {len(self.patterns)}\n\n")

        # Call graph summary
        prompt.append("## Call Graph Structure\n")
        for fn, callees in self.analyzer.call_graph.items():
            if callees:
                prompt.append(f"- {fn} -> {', '.join(sorted(callees))}\n")
        prompt.append("\n")

        # Behavioral patterns
        prompt.append("## Behavioral Patterns\n")
        for pattern in self.patterns:
            prompt.append(f"### {pattern.name}\n")
            prompt.append(f"- Type: {pattern.type}\n")
            prompt.append(f"- Entry points: {', '.join(pattern.entry_points)}\n")
            prompt.append(f"- Decision points: {', '.join(pattern.decision_points)}\n")
            prompt.append(f"- Confidence: {pattern.confidence:.2f}\n\n")

        # Data flow insights
        prompt.append("## Data Flow Insights\n")
        for var, deps in self.analyzer.data_dependencies.items():
            if deps:
                prompt.append(f"- {var} depends on: {', '.join(sorted(deps))}\n")
        prompt.append("\n")

        # State machines
        if self.analyzer.state_machines:
            prompt.append("## State Machines\n")
            for sm in self.analyzer.state_machines:
                prompt.append(f"### {sm['name']}\n")
                prompt.append(f"- States: {', '.join(sm['states'])}\n")
                prompt.append(f"- Transitions: {len(sm['transitions'])}\n")
                for t in sm["transitions"]:
                    prompt.append(
                        f"  - {t['method']}: {t['from_state']} -> {t['to_state']}\n"
                    )
                prompt.append("\n")

        # Reverse engineering guidance
        prompt.append("## Reverse Engineering Guidelines\n")
        prompt.append("1. Preserve the call graph structure\n")
        prompt.append("2. Implement identified behavioral patterns\n")
        prompt.append("3. Maintain data dependencies\n")
        prompt.append("4. Recreate state machines with same transitions\n")
        prompt.append("5. Keep decision logic in conditional patterns\n\n")

        return "".join(prompt)

    def generate_diagram_data(self) -> Dict:
        """Generate diagram data for visualization."""
        diagram_data = {"nodes": [], "edges": [], "patterns": [], "clusters": []}

        # Convert nodes
        for node_id, node in self.analyzer.nodes.items():
            diagram_data["nodes"].append(
                {
                    "id": node_id,
                    "label": node.label,
                    "type": node.type,
                    "function": node.function,
                    "file": node.file,
                    "line": node.line,
                }
            )

        # Convert edges
        for src, dsts in self.analyzer.cfg.items():
            for dst in dsts:
                diagram_data["edges"].append({"from": src, "to": dst})

        # Pattern information
        for pattern in self.patterns:
            diagram_data["patterns"].append(
                {
                    "name": pattern.name,
                    "type": pattern.type,
                    "confidence": pattern.confidence,
                }
            )

        return diagram_data

    def export_yaml(self, filename: str):
        """Export analysis in YAML format for LLM consumption."""
        import yaml

        data = {
            "metadata": {
                "timestamp": time.time(),
                "total_functions": len(self.analyzer.function_entries),
                "total_patterns": len(self.patterns),
            },
            "call_graph": {k: list(v) for k, v in self.analyzer.call_graph.items()},
            "patterns": [asdict(p) for p in self.patterns],
            "state_machines": self.analyzer.state_machines,
            "data_dependencies": {
                k: list(v) for k, v in self.analyzer.data_dependencies.items()
            },
        }

        with open(filename, "w") as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)

    def export_mermaid(self, filename: str):
        """Export flow diagram as Mermaid diagram."""
        mermaid = ["graph TD"]

        # Add nodes
        for node_id, node in self.analyzer.nodes.items():
            label = node.label.replace('"', '\\"')
            node_type = node.type.lower()
            mermaid.append(f'    {node_id}["{label}"]:::{node_type}')

        # Add edges
        for src, dsts in self.analyzer.cfg.items():
            for dst in dsts:
                mermaid.append(f"    {src} --> {dst}")

        # Add styling
        mermaid.append("\n    classDef func fill:#e1f5fe")
        mermaid.append("    classDef call fill:#f3e5f5")
        mermaid.append("    classDef if fill:#fff3e0")
        mermaid.append("    classDef return fill:#e8f5e8")

        # Apply styles
        for node_id, node in self.analyzer.nodes.items():
            node_type = node.type.lower()
            if node_type in ["func", "call", "if", "return"]:
                mermaid.append(f"    class {node_id} {node_type}")

        with open(filename, "w") as f:
            f.write("\n".join(mermaid))


# =====================================================
# Visualizer
# =====================================================


class FlowVisualizer:
    """Visualize flow analysis results."""

    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.G = nx.DiGraph()
        self._build_graph()

    def _build_graph(self):
        """Build NetworkX graph from analysis."""
        # Add nodes
        for node_id, node in self.analyzer.nodes.items():
            self.G.add_node(
                node_id, label=node.label, type=node.type, function=node.function
            )

        # Add edges
        for src, dsts in self.analyzer.cfg.items():
            for dst in dsts:
                self.G.add_edge(src, dst)

    def visualize_flow(self, filename: str, layout="spring"):
        """Create flow visualization."""
        plt.figure(figsize=(16, 12))

        # Choose layout
        if layout == "spring":
            pos = nx.spring_layout(self.G, k=2, iterations=50)
        elif layout == "hierarchical":
            pos = self._hierarchical_layout()
        else:
            pos = nx.random_layout(self.G)

        # Draw nodes by type
        node_colors = []
        for node_id in self.G.nodes():
            node_type = self.G.nodes[node_id]["type"]
            if node_type == "FUNC":
                node_colors.append("#4CAF50")
            elif node_type == "CALL":
                node_colors.append("#2196F3")
            elif node_type == "IF":
                node_colors.append("#FF9800")
            elif node_type == "RETURN":
                node_colors.append("#9C27B0")
            else:
                node_colors.append("#757575")

        # Draw graph
        nx.draw_networkx_nodes(
            self.G, pos, node_color=node_colors, node_size=500, alpha=0.8
        )
        nx.draw_networkx_edges(
            self.G, pos, alpha=0.4, arrows=True, arrowsize=20, arrowstyle="->"
        )

        # Draw labels for important nodes only
        labels = {}
        for node_id in self.G.nodes():
            node = self.G.nodes[node_id]
            if node["type"] in ["FUNC", "IF"]:
                labels[node_id] = node["label"].split(":")[-1][:20]

        nx.draw_networkx_labels(self.G, pos, labels, font_size=8)

        # Add legend
        legend_elements = [
            patches.Patch(color="#4CAF50", label="Function"),
            patches.Patch(color="#2196F3", label="Call"),
            patches.Patch(color="#FF9800", label="Decision"),
            patches.Patch(color="#9C27B0", label="Return"),
        ]
        plt.legend(handles=legend_elements, loc="upper right")

        plt.title("System Control Flow Analysis", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close()

    def _hierarchical_layout(self):
        """Create hierarchical layout for better visualization."""
        # Group nodes by function
        function_groups = defaultdict(list)
        for node_id, node in self.analyzer.nodes.items():
            if node.function:
                function_groups[node.function].append(node_id)

        # Position nodes hierarchically
        pos = {}
        y_offset = 0
        x_offset = 0

        for func_name, nodes in function_groups.items():
            for i, node_id in enumerate(nodes):
                pos[node_id] = (x_offset + i * 2, -y_offset)
            y_offset += 3
            if len(nodes) > 5:
                x_offset = 0

        return pos


# =====================================================
# Main Analyzer
# =====================================================


class ProjectFlowAnalyzer:
    """Main project flow analyzer combining all techniques."""

    def __init__(self, mode: str = "hybrid"):
        self.mode = mode
        self.static_analyzers = {}
        self.dynamic_tracer = DynamicTracer()
        self.patterns = []

    def analyze_project(self, src_root: str, output_dir: str = "output"):
        """Analyze entire project."""
        os.makedirs(output_dir, exist_ok=True)

        print(f"Analyzing project in {src_root}...")
        print(f"Mode: {MODES.get(self.mode, self.mode)}")

        # Phase 1: Static analysis
        print("\n=== Static Analysis ===")
        self._static_analysis(src_root)

        # Phase 2: Dynamic analysis (if requested)
        if self.mode in ["dynamic", "hybrid"]:
            print("\n=== Dynamic Analysis ===")
            self._dynamic_analysis(src_root)

        # Phase 3: Pattern extraction
        print("\n=== Pattern Extraction ===")
        self._extract_patterns()

        # Phase 4: Generate outputs
        print("\n=== Generating Outputs ===")
        self._generate_outputs(output_dir)

        print(f"\nAnalysis complete. Results saved to {output_dir}/")

    def _static_analysis(self, src_root: str):
        """Perform static analysis on all Python files."""
        py_files = []
        for root, _, files in os.walk(src_root):
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        print(f"Found {len(py_files)} Python files")

        for i, path in enumerate(py_files):
            if i % 50 == 0:
                print(f"Processed {i}/{len(py_files)} files...")

            module = self._module_name_from_path(src_root, path)

            try:
                with open(path, "r", encoding="utf8") as f:
                    code = f.read()

                tree = ast.parse(code, filename=path)
                analyzer = EnhancedFlowExtractor(module, path)
                analyzer.function_entries = {}
                analyzer.visit(tree)

                self.static_analyzers[module] = analyzer

            except Exception as e:
                print(f"[WARN] {path}: {e}")

    def _dynamic_analysis(self, src_root: str):
        """Perform dynamic analysis by running tests."""
        # Look for test files
        test_files = []
        for root, _, files in os.walk(src_root):
            for f in files:
                if "test" in f.lower() and f.endswith(".py"):
                    test_files.append(os.path.join(root, f))

        if not test_files:
            print("No test files found for dynamic analysis")
            return

        print(f"Running {len(test_files)} test files with tracing...")

        # Run tests with tracing
        self.dynamic_tracer.start_tracing()

        for test_file in test_files[:3]:  # Limit to avoid too much data
            try:
                subprocess.run(
                    [sys.executable, test_file], capture_output=True, timeout=30
                )
            except Exception:
                pass

        self.dynamic_tracer.stop_tracing()
        print(f"Collected {len(self.dynamic_tracer.traces)} execution traces")

    def _extract_patterns(self):
        """Extract behavioral patterns from analysis."""
        all_patterns = []

        for module, analyzer in self.static_analyzers.items():
            extractor = BehavioralPatternExtractor(analyzer, self.dynamic_tracer)
            patterns = extractor.extract_patterns()
            all_patterns.extend(patterns)

        self.patterns = all_patterns
        print(f"Extracted {len(self.patterns)} behavioral patterns")

    def _generate_outputs(self, output_dir: str):
        """Generate all output files."""
        # Combine all analyzers
        combined = self._combine_analyzers()

        # Generate reverse engineering output
        regen = ReverseEngineeringGenerator(combined, self.patterns)

        # LLM prompt
        prompt = regen.generate_llm_prompt()
        with open(f"{output_dir}/system_analysis_prompt.md", "w") as f:
            f.write(prompt)

        # YAML export
        regen.export_yaml(f"{output_dir}/system_analysis.yaml")

        # Mermaid diagram
        regen.export_mermaid(f"{output_dir}/system_flow.mmd")

        # Visualization
        visualizer = FlowVisualizer(combined)
        visualizer.visualize_flow(f"{output_dir}/system_flow.png")

        # Diagram data
        diagram_data = regen.generate_diagram_data()
        with open(f"{output_dir}/diagram_data.json", "w") as f:
            json.dump(diagram_data, f, indent=2)

        # Summary report
        self._generate_summary_report(output_dir)

    def _combine_analyzers(self) -> EnhancedFlowExtractor:
        """Combine all static analyzers into one."""
        combined = EnhancedFlowExtractor("combined", "")
        combined.node_id = 0

        for analyzer in self.static_analyzers.values():
            # Merge nodes
            offset = combined.node_id
            for old_id, node in analyzer.nodes.items():
                new_id = old_id + offset
                combined.nodes[new_id] = node
                combined.nodes[new_id].id = new_id

            # Merge CFG
            for src, dsts in analyzer.cfg.items():
                for dst in dsts:
                    combined.cfg[src + offset].append(dst + offset)

            # Merge call graph
            for fn, callees in analyzer.call_graph.items():
                combined.call_graph[fn].update(callees)

            # Merge function entries
            combined.function_entries.update(analyzer.function_entries)

            # Merge data dependencies
            for var, deps in analyzer.data_dependencies.items():
                combined.data_dependencies[var].update(deps)

            # Update node offset
            combined.node_id += len(analyzer.nodes)

        return combined

    def _generate_summary_report(self, output_dir: str):
        """Generate summary report."""
        report = []
        report.append("# Project Flow Analysis Report\n")
        report.append(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.append(f"Analysis mode: {self.mode}\n\n")

        # Statistics
        total_functions = sum(
            len(a.function_entries) for a in self.static_analyzers.values()
        )
        total_nodes = sum(len(a.nodes) for a in self.static_analyzers.values())
        total_edges = sum(
            sum(len(v) for v in a.cfg.values()) for a in self.static_analyzers.values()
        )

        report.append("## Statistics\n")
        report.append(f"- Modules analyzed: {len(self.static_analyzers)}\n")
        report.append(f"- Total functions: {total_functions}\n")
        report.append(f"- Total CFG nodes: {total_nodes}\n")
        report.append(f"- Total CFG edges: {total_edges}\n")
        report.append(f"- Behavioral patterns: {len(self.patterns)}\n\n")

        # Pattern summary
        pattern_types = defaultdict(int)
        for pattern in self.patterns:
            pattern_types[pattern.type] += 1

        report.append("## Pattern Distribution\n")
        for ptype, count in pattern_types.items():
            report.append(f"- {ptype}: {count}\n")
        report.append("\n")

        # Complex functions (most connections)
        combined = self._combine_analyzers()
        function_complexity = defaultdict(int)

        for node_id, node in combined.nodes.items():
            if node.function:
                function_complexity[node.function] += len(combined.cfg.get(node_id, []))

        report.append("## Most Complex Functions\n")
        for func, complexity in sorted(
            function_complexity.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            report.append(f"- {func}: {complexity} connections\n")

        with open(f"{output_dir}/analysis_report.md", "w") as f:
            f.write("".join(report))

    def _module_name_from_path(self, root: str, path: str) -> str:
        """Convert file path to module name."""
        rel = os.path.relpath(path, root)
        rel = rel.replace(os.sep, ".")
        if rel.endswith(".py"):
            rel = rel[:-3]
        if rel.endswith(".__init__"):
            rel = rel[:-9]
        return rel


# =====================================================
# CLI Interface
# =====================================================


def main():
    """Command line interface."""
    import argparse

    parser = argparse.ArgumentParser(description="Advanced Project Flow Analyzer")
    parser.add_argument("src_root", help="Source code root directory")
    parser.add_argument(
        "-m",
        "--mode",
        choices=list(MODES.keys()),
        default="hybrid",
        help="Analysis mode",
    )
    parser.add_argument(
        "-o", "--output", default="flow_analysis_output", help="Output directory"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not os.path.exists(args.src_root):
        print(f"Error: Source directory {args.src_root} does not exist")
        sys.exit(1)

    # Run analysis
    analyzer = ProjectFlowAnalyzer(mode=args.mode)
    analyzer.analyze_project(args.src_root, args.output)

    print("\n=== Analysis Complete ===")
    print(f"Outputs generated in: {args.output}/")
    print("Files generated:")
    print("- system_analysis_prompt.md (LLM-ready system description)")
    print("- system_analysis.yaml (Structured analysis data)")
    print("- system_flow.mmd (Mermaid diagram)")
    print("- system_flow.png (Flow visualization)")
    print("- diagram_data.json (Raw diagram data)")
    print("- analysis_report.md (Summary report)")


if __name__ == "__main__":
    main()
