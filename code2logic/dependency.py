"""
Dependency graph analyzer using NetworkX.

Builds and analyzes dependency graphs from module imports,
computing metrics like PageRank, centrality, and clustering.
"""

from pathlib import Path
from typing import Dict, List

from .models import DependencyNode, ModuleInfo

# Optional NetworkX import
NETWORKX_AVAILABLE = False
try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    nx = None


class DependencyAnalyzer:
    """
    Analyzes dependency graphs using NetworkX.

    Computes:
    - PageRank: Importance metric for modules
    - In/Out degree: Number of dependencies
    - Hub detection: Identifies central modules
    - Clustering: Groups related modules

    Example:
        >>> analyzer = DependencyAnalyzer()
        >>> graph = analyzer.build_graph(modules)
        >>> metrics = analyzer.analyze_metrics()
        >>> hubs = [p for p, n in metrics.items() if n.is_hub]
    """

    def __init__(self):
        """Initialize the dependency analyzer."""
        self.graph = None
        if NETWORKX_AVAILABLE:
            self.graph = nx.DiGraph()

    def build_graph(self, modules: List[ModuleInfo]) -> Dict[str, List[str]]:
        """
        Build dependency graph from modules.

        Args:
            modules: List of ModuleInfo objects

        Returns:
            Dict mapping module path to list of dependency paths
        """
        simple_graph: Dict[str, List[str]] = {}
        module_names: Dict[str, str] = {}

        # Build module name mapping
        for m in modules:
            name = self._module_name(m.path)
            stem = Path(m.path).stem
            module_names[name] = m.path
            module_names[m.path] = m.path
            if stem not in module_names:
                module_names[stem] = m.path

        # Build graph
        for module in modules:
            deps: set = set()
            for imp in module.imports:
                imp_clean = imp.replace("/", ".").replace("\\", ".").lstrip(".")
                parts = imp_clean.split(".")

                for i in range(len(parts), 0, -1):
                    candidate = ".".join(parts[:i])
                    if (
                        candidate in module_names
                        and module_names[candidate] != module.path
                    ):
                        deps.add(module_names[candidate])
                        break

            simple_graph[module.path] = list(deps)

            # Add to NetworkX if available
            if self.graph is not None:
                self.graph.add_node(module.path)
                for dep in deps:
                    self.graph.add_edge(module.path, dep)

        return simple_graph

    def analyze_metrics(self) -> Dict[str, DependencyNode]:
        """
        Compute metrics for each node in the graph.

        Returns:
            Dict mapping module path to DependencyNode with metrics
        """
        metrics: Dict[str, DependencyNode] = {}

        if self.graph is None or len(self.graph.nodes) == 0:
            return metrics

        # PageRank
        try:
            pagerank = nx.pagerank(self.graph, alpha=0.85)
        except Exception:
            pagerank = dict.fromkeys(self.graph.nodes, 0.0)

        # Degree metrics
        in_deg = dict(self.graph.in_degree())
        out_deg = dict(self.graph.out_degree())

        # Average PageRank for hub detection
        avg_pr = sum(pagerank.values()) / len(pagerank) if pagerank else 0

        # Clustering
        clusters = self._detect_clusters()

        for node in self.graph.nodes:
            metrics[node] = DependencyNode(
                path=node,
                in_degree=in_deg.get(node, 0),
                out_degree=out_deg.get(node, 0),
                pagerank=pagerank.get(node, 0.0),
                is_hub=pagerank.get(node, 0) > avg_pr * 2,
                cluster=clusters.get(node, 0),
            )

        return metrics

    def get_entrypoints(self) -> List[str]:
        """
        Get entry points (nodes with no incoming edges).

        Returns:
            List of module paths that are entry points
        """
        if self.graph is None:
            return []
        return [n for n in self.graph.nodes if self.graph.in_degree(n) == 0]

    def get_hubs(self) -> List[str]:
        """
        Get hub modules (high centrality).

        Returns:
            List of module paths that are hubs
        """
        metrics = self.analyze_metrics()
        return [path for path, node in metrics.items() if node.is_hub]

    def detect_cycles(self) -> List[List[str]]:
        """
        Detect dependency cycles.

        Returns:
            List of cycles (each cycle is a list of paths)
        """
        if self.graph is None:
            return []

        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles[:10]  # Limit to top 10
        except Exception:
            return []

    def get_strongly_connected_components(self) -> List[List[str]]:
        """
        Get strongly connected components.

        Returns:
            List of components (each component is a list of paths)
        """
        if self.graph is None:
            return []

        try:
            components = list(nx.strongly_connected_components(self.graph))
            return [list(c) for c in components if len(c) > 1]
        except Exception:
            return []

    def _detect_clusters(self) -> Dict[str, int]:
        """Detect clusters using connected components."""
        if self.graph is None:
            return {}

        try:
            undirected = self.graph.to_undirected()
            components = list(nx.connected_components(undirected))

            clusters = {}
            for i, component in enumerate(components):
                for node in component:
                    clusters[node] = i

            return clusters
        except Exception:
            return {}

    def _module_name(self, path: str) -> str:
        """Convert file path to module name."""
        name = path.replace("/", ".").replace("\\", ".")
        for ext in [".py", ".js", ".ts", ".jsx", ".tsx"]:
            if name.endswith(ext):
                name = name[: -len(ext)]
        return name

    def get_dependency_depth(self, module_path: str) -> int:
        """
        Get the maximum depth of dependencies for a module.

        Args:
            module_path: Path to the module

        Returns:
            Maximum dependency depth
        """
        if self.graph is None or module_path not in self.graph:
            return 0

        try:
            # BFS to find max depth
            visited = {module_path}
            current_level = [module_path]
            depth = 0

            while current_level:
                next_level = []
                for node in current_level:
                    for neighbor in self.graph.successors(node):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_level.append(neighbor)
                if next_level:
                    depth += 1
                current_level = next_level

            return depth
        except Exception:
            return 0


def is_networkx_available() -> bool:
    """Check if NetworkX is available."""
    return NETWORKX_AVAILABLE
