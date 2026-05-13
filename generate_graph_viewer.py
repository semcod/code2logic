#!/usr/bin/env python3
"""
Generate interactive graph viewer with zoom/pan functionality from YAML files.
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
import math


class GraphGenerator:
    """Generate interactive graph visualization from YAML data."""

    def __init__(self, hybrid_path: str):
        self.hybrid_path = Path(hybrid_path)
        self.graph_data = {}

    def generate_graph_viewer(self):
        """Generate complete interactive graph viewer."""

        print("🔄 Generating interactive graph viewer...")

        # Load data from hybrid export
        self.load_hybrid_data()

        # Build graph structure
        graph_structure = self.build_graph_structure()

        # Generate HTML with embedded graph
        html_content = self.generate_graph_html(graph_structure)

        # Save graph viewer
        output_path = self.hybrid_path / "graph_viewer.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"✓ Graph viewer generated: {output_path}")
        print(f"  • Size: {output_path.stat().st_size / 1024:.1f}K")
        print(f"  • Nodes: {len(graph_structure['nodes'])}")
        print(f"  • Edges: {len(graph_structure['edges'])}")
        print("  • Features: Zoom, Pan, Search, Filter")

        return output_path

    def load_hybrid_data(self):
        """Load data from hybrid export files."""

        # Load index
        index_path = self.hybrid_path / "index.yaml"
        with open(index_path, "r") as f:
            self.graph_data["index"] = yaml.safe_load(f)

        # Load consolidated summary
        consolidated_summary = self.hybrid_path / "consolidated" / "summary.yaml"
        if consolidated_summary.exists():
            with open(consolidated_summary, "r") as f:
                self.graph_data["consolidated"] = yaml.safe_load(f)

        # Load orphans summary
        orphans_summary = self.hybrid_path / "orphans" / "summary.yaml"
        if orphans_summary.exists():
            with open(orphans_summary, "r") as f:
                self.graph_data["orphans"] = yaml.safe_load(f)

        # Load sample function files for graph building
        self.load_sample_files()

    def load_sample_files(self):
        """Load sample files to build graph connections."""

        self.graph_data["functions"] = {}
        self.graph_data["connections"] = []

        # Load consolidated functions (sample)
        consolidated_dir = self.hybrid_path / "consolidated"
        if consolidated_dir.exists():
            consolidated_files = list(consolidated_dir.glob("functions_*.yaml"))[
                :20
            ]  # Limit to 20 files
            for file_path in consolidated_files:
                try:
                    with open(file_path, "r") as f:
                        data = yaml.safe_load(f)
                        if "functions" in data:
                            self.graph_data["functions"].update(data["functions"])
                except Exception as e:
                    print(f"Warning: Could not load {file_path}: {e}")

        # Build connections from function data
        self.build_connections()

    def build_connections(self):
        """Build graph connections from function data."""

        functions = self.graph_data.get("functions", {})

        for func_name, func_data in functions.items():
            if isinstance(func_data, dict):
                # Extract calls information
                calls = func_data.get("calls", [])
                called_by = func_data.get("called_by", [])

                # Add outgoing edges
                for called in calls[:10]:  # Limit connections
                    self.graph_data["connections"].append(
                        {"from": func_name, "to": called, "type": "call", "weight": 1}
                    )

                # Add incoming edges
                for caller in called_by[:10]:
                    self.graph_data["connections"].append(
                        {
                            "from": caller,
                            "to": func_name,
                            "type": "called_by",
                            "weight": 1,
                        }
                    )

    def build_graph_structure(self) -> Dict[str, Any]:
        """Build graph structure for visualization."""

        nodes = []
        edges = []
        node_map = {}

        # Process connections to build nodes and edges
        processed_connections = self.graph_data.get("connections", [])

        # Create nodes
        for conn in processed_connections:
            for node_name in [conn["from"], conn["to"]]:
                if node_name not in node_map:
                    node_id = len(nodes)
                    node_map[node_name] = node_id

                    # Determine node category
                    category = self.get_node_category(node_name)

                    # Calculate position (force-directed layout simulation)
                    x, y = self.calculate_position(node_name, len(nodes))

                    nodes.append(
                        {
                            "id": node_id,
                            "name": node_name.split(".")[-1],  # Short name
                            "full_name": node_name,
                            "category": category,
                            "x": x,
                            "y": y,
                            "vx": 0,
                            "vy": 0,
                            "connections": 0,
                            "radius": self.calculate_radius(node_name),
                        }
                    )

        # Create edges
        edge_map = {}
        for conn in processed_connections:
            from_node = node_map.get(conn["from"])
            to_node = node_map.get(conn["to"])

            if from_node is not None and to_node is not None:
                edge_key = f"{min(from_node, to_node)}-{max(from_node, to_node)}"
                if edge_key not in edge_map:
                    edge_map[edge_key] = {
                        "source": from_node,
                        "target": to_node,
                        "weight": 0,
                        "type": conn["type"],
                    }
                edge_map[edge_key]["weight"] += 1

                # Update node connection counts
                nodes[from_node]["connections"] += 1
                nodes[to_node]["connections"] += 1

        edges = list(edge_map.values())

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "categories": self.get_category_stats(nodes),
            },
        }

    def get_node_category(self, node_name: str) -> str:
        """Determine node category based on name."""

        name_lower = node_name.lower()

        if "automation" in name_lower:
            return "automation"
        elif "pipeline" in name_lower:
            return "pipeline"
        elif "generation" in name_lower:
            return "generation"
        elif "llm" in name_lower:
            return "llm"
        elif "validator" in name_lower:
            return "validator"
        elif "adapter" in name_lower:
            return "adapter"
        elif "executor" in name_lower:
            return "executor"
        else:
            return "other"

    def calculate_position(self, node_name: str, index: int) -> Tuple[float, float]:
        """Calculate initial position for node."""

        # Simple circular layout with some randomness
        angle = (index * 137.5) * math.pi / 180  # Golden angle
        radius = 200 + (index % 5) * 50

        x = 400 + radius * math.cos(angle)
        y = 300 + radius * math.sin(angle)

        return x, y

    def calculate_radius(self, node_name: str) -> float:
        """Calculate node radius based on importance."""

        name_lower = node_name.lower()

        if any(keyword in name_lower for keyword in ["runner", "main", "init"]):
            return 12
        elif any(
            keyword in name_lower for keyword in ["planner", "executor", "generator"]
        ):
            return 10
        else:
            return 8

    def get_category_stats(self, nodes: List[Dict]) -> Dict[str, int]:
        """Get statistics by category."""

        stats = {}
        for node in nodes:
            category = node["category"]
            stats[category] = stats.get(category, 0) + 1

        return stats

    def generate_graph_html(self, graph_structure: Dict[str, Any]) -> str:
        """Generate complete HTML with interactive graph."""

        # Convert to JSON for embedding
        graph_json = json.dumps(graph_structure, indent=2)

        html_template = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Graph Viewer - Code Analysis</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
            overflow: hidden;
        }}

        .container {{
            display: flex;
            height: 100vh;
        }}

        .sidebar {{
            width: 300px;
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            overflow-y: auto;
            box-shadow: 2px 0 10px rgba(0, 0, 0, 0.1);
        }}

        .main-content {{
            flex: 1;
            position: relative;
        }}

        .header {{
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 10px;
            text-align: center;
        }}

        .header h1 {{
            color: #4a5568;
            font-size: 1.8em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .controls {{
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}

        .control-group {{
            margin-bottom: 15px;
        }}

        .control-group label {{
            display: block;
            margin-bottom: 5px;
            color: #4a5568;
            font-weight: 500;
        }}

        .control-group input,
        .control-group select {{
            width: 100%;
            padding: 8px 12px;
            border: 2px solid #e2e8f0;
            border-radius: 6px;
            font-size: 0.9em;
        }}

        .control-group input:focus,
        .control-group select:focus {{
            outline: none;
            border-color: #667eea;
        }}

        .btn {{
            width: 100%;
            padding: 10px;
            border: none;
            border-radius: 6px;
            background: #667eea;
            color: white;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}

        .btn:hover {{
            background: #5a67d8;
            transform: translateY(-1px);
        }}

        .btn.secondary {{
            background: #e2e8f0;
            color: #4a5568;
        }}

        .btn.secondary:hover {{
            background: #cbd5e0;
        }}

        #graphCanvas {{
            width: 100%;
            height: 100%;
            cursor: grab;
        }}

        #graphCanvas:active {{
            cursor: grabbing;
        }}

        .stats {{
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}

        .stat-item {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            padding: 5px 0;
            border-bottom: 1px solid #e2e8f0;
        }}

        .stat-item:last-child {{
            border-bottom: none;
        }}

        .stat-label {{
            color: #718096;
            font-size: 0.9em;
        }}

        .stat-value {{
            color: #4a5568;
            font-weight: 600;
        }}

        .legend {{
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            border-radius: 10px;
        }}

        .legend-title {{
            font-weight: 600;
            color: #4a5568;
            margin-bottom: 10px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }}

        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            margin-right: 8px;
        }}

        .legend-label {{
            color: #718096;
            font-size: 0.9em;
        }}

        .tooltip {{
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 10px;
            border-radius: 6px;
            font-size: 0.9em;
            pointer-events: none;
            z-index: 1000;
            display: none;
            max-width: 250px;
        }}

        .zoom-controls {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }}

        .zoom-btn {{
            width: 40px;
            height: 40px;
            border: none;
            border-radius: 6px;
            background: #667eea;
            color: white;
            cursor: pointer;
            margin: 2px;
            font-size: 1.2em;
            transition: all 0.3s ease;
        }}

        .zoom-btn:hover {{
            background: #5a67d8;
            transform: scale(1.1);
        }}

        @media (max-width: 768px) {{
            .container {{
                flex-direction: column;
            }}
            
            .sidebar {{
                width: 100%;
                height: 300px;
            }}
            
            .main-content {{
                height: calc(100vh - 300px);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <div class="header">
                <h1>🔗 Graph Viewer</h1>
                <p>Interactive code analysis graph</p>
            </div>

            <div class="controls">
                <div class="control-group">
                    <label for="searchInput">🔍 Search Nodes</label>
                    <input type="text" id="searchInput" placeholder="Type to search...">
                </div>

                <div class="control-group">
                    <label for="categoryFilter">📊 Filter by Category</label>
                    <select id="categoryFilter">
                        <option value="all">All Categories</option>
                    </select>
                </div>

                <div class="control-group">
                    <label for="layoutType">🎯 Layout Type</label>
                    <select id="layoutType">
                        <option value="force">Force Directed</option>
                        <option value="circular">Circular</option>
                        <option value="hierarchical">Hierarchical</option>
                    </select>
                </div>

                <button class="btn" onclick="resetView()">🔄 Reset View</button>
                <button class="btn secondary" onclick="toggleAnimation()">▶️ Toggle Animation</button>
                <button class="btn secondary" onclick="exportGraph()">📥 Export Graph</button>
            </div>

            <div class="stats" id="stats">
                <div class="stat-item">
                    <span class="stat-label">Total Nodes</span>
                    <span class="stat-value" id="totalNodes">0</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Total Edges</span>
                    <span class="stat-value" id="totalEdges">0</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Visible Nodes</span>
                    <span class="stat-value" id="visibleNodes">0</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Zoom Level</span>
                    <span class="stat-value" id="zoomLevel">100%</span>
                </div>
            </div>

            <div class="legend">
                <div class="legend-title">Categories</div>
                <div id="legendItems"></div>
            </div>
        </div>

        <div class="main-content">
            <canvas id="graphCanvas"></canvas>
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="zoomIn()">+</button>
                <button class="zoom-btn" onclick="zoomOut()">-</button>
                <button class="zoom-btn" onclick="fitToScreen()">⊡</button>
            </div>
            <div class="tooltip" id="tooltip"></div>
        </div>
    </div>

    <script>
        // Embedded graph data
        window.graphData = {graph_json};

        // Graph visualization class
        class GraphViewer {{
            constructor(canvasId, data) {{
                this.canvas = document.getElementById(canvasId);
                this.ctx = this.canvas.getContext('2d');
                this.data = data;
                this.nodes = data.nodes;
                this.edges = data.edges;
                
                // Visualization state
                this.zoom = 1.0;
                this.offsetX = 0;
                this.offsetY = 0;
                this.isDragging = false;
                this.dragStartX = 0;
                this.dragStartY = 0;
                this.animationRunning = false;
                this.selectedNode = null;
                
                // Colors for categories
                this.colors = {{
                    automation: '#e53e3e',
                    pipeline: '#38a169',
                    generation: '#3182ce',
                    llm: '#805ad5',
                    validator: '#d69e2e',
                    adapter: '#dd6b20',
                    executor: '#2d3748',
                    other: '#718096'
                }};
                
                this.init();
            }}
            
            init() {{
                this.resizeCanvas();
                this.setupEventListeners();
                this.populateFilters();
                this.updateStats();
                this.animate();
            }}
            
            resizeCanvas() {{
                this.canvas.width = this.canvas.offsetWidth;
                this.canvas.height = this.canvas.offsetHeight;
            }}
            
            setupEventListeners() {{
                // Window resize
                window.addEventListener('resize', () => this.resizeCanvas());
                
                // Mouse events
                this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
                this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
                this.canvas.addEventListener('mouseup', (e) => this.onMouseUp(e));
                this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
                
                // Touch events
                this.canvas.addEventListener('touchstart', (e) => this.onTouchStart(e));
                this.canvas.addEventListener('touchmove', (e) => this.onTouchMove(e));
                this.canvas.addEventListener('touchend', (e) => this.onTouchEnd(e));
                
                // Search
                document.getElementById('searchInput').addEventListener('input', (e) => this.onSearch(e));
                
                // Category filter
                document.getElementById('categoryFilter').addEventListener('change', (e) => this.onCategoryFilter(e));
                
                // Layout type
                document.getElementById('layoutType').addEventListener('change', (e) => this.onLayoutChange(e));
            }}
            
            onMouseDown(e) {{
                const rect = this.canvas.getBoundingClientRect();
                const x = (e.clientX - rect.left - this.offsetX) / this.zoom;
                const y = (e.clientY - rect.top - this.offsetY) / this.zoom;
                
                // Check if clicking on a node
                this.selectedNode = this.getNodeAt(x, y);
                
                if (this.selectedNode) {{
                    this.showTooltip(e.clientX, e.clientY, this.selectedNode);
                }} else {{
                    this.hideTooltip();
                    this.isDragging = true;
                    this.dragStartX = e.clientX - this.offsetX;
                    this.dragStartY = e.clientY - this.offsetY;
                }}
            }}
            
            onMouseMove(e) {{
                const rect = this.canvas.getBoundingClientRect();
                const x = (e.clientX - rect.left - this.offsetX) / this.zoom;
                const y = (e.clientY - rect.top - this.offsetY) / this.zoom;
                
                if (this.isDragging) {{
                    this.offsetX = e.clientX - this.dragStartX;
                    this.offsetY = e.clientY - this.dragStartY;
                }} else {{
                    // Hover effect
                    const hoveredNode = this.getNodeAt(x, y);
                    if (hoveredNode) {{
                        this.canvas.style.cursor = 'pointer';
                    }} else {{
                        this.canvas.style.cursor = 'grab';
                    }}
                }}
            }}
            
            onMouseUp(e) {{
                this.isDragging = false;
            }}
            
            onWheel(e) {{
                e.preventDefault();
                const delta = e.deltaY > 0 ? 0.9 : 1.1;
                this.zoom *= delta;
                this.zoom = Math.max(0.1, Math.min(5, this.zoom));
                this.updateZoomLevel();
            }}
            
            onTouchStart(e) {{
                if (e.touches.length === 1) {{
                    const touch = e.touches[0];
                    this.onMouseDown({{ clientX: touch.clientX, clientY: touch.clientY }});
                }}
            }}
            
            onTouchMove(e) {{
                if (e.touches.length === 1) {{
                    e.preventDefault();
                    const touch = e.touches[0];
                    this.onMouseMove({{ clientX: touch.clientX, clientY: touch.clientY }});
                }}
            }}
            
            onTouchEnd(e) {{
                this.onMouseUp({{}});
            }}
            
            getNodeAt(x, y) {{
                for (const node of this.nodes) {{
                    const dx = x - node.x;
                    const dy = y - node.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    if (distance <= node.radius) {{
                        return node;
                    }}
                }}
                return null;
            }}
            
            showTooltip(x, y, node) {{
                const tooltip = document.getElementById('tooltip');
                tooltip.innerHTML = `
                    <strong>${{node.name}}</strong><br>
                    <small>${{node.full_name}}</small><br>
                    Category: ${{node.category}}<br>
                    Connections: ${{node.connections}}
                `;
                tooltip.style.left = x + 10 + 'px';
                tooltip.style.top = y - 10 + 'px';
                tooltip.style.display = 'block';
            }}
            
            hideTooltip() {{
                document.getElementById('tooltip').style.display = 'none';
            }}
            
            onSearch(e) {{
                const query = e.target.value.toLowerCase();
                this.nodes.forEach(node => {{
                    node.visible = query === '' || 
                        node.name.toLowerCase().includes(query) ||
                        node.full_name.toLowerCase().includes(query);
                }});
                this.updateStats();
            }}
            
            onCategoryFilter(e) {{
                const category = e.target.value;
                this.nodes.forEach(node => {{
                    node.visible = category === 'all' || node.category === category;
                }});
                this.updateStats();
            }}
            
            onLayoutChange(e) {{
                const layoutType = e.target.value;
                this.applyLayout(layoutType);
            }}
            
            applyLayout(type) {{
                switch(type) {{
                    case 'circular':
                        this.applyCircularLayout();
                        break;
                    case 'hierarchical':
                        this.applyHierarchicalLayout();
                        break;
                    case 'force':
                    default:
                        this.applyForceLayout();
                        break;
                }}
            }}
            
            applyCircularLayout() {{
                const centerX = this.canvas.width / 2;
                const centerY = this.canvas.height / 2;
                const radius = Math.min(centerX, centerY) - 100;
                
                this.nodes.forEach((node, i) => {{
                    const angle = (i / this.nodes.length) * 2 * Math.PI;
                    node.x = centerX + radius * Math.cos(angle);
                    node.y = centerY + radius * Math.sin(angle);
                }});
            }}
            
            applyHierarchicalLayout() {{
                const levels = {{}};
                const visited = new Set();
                
                // Simple topological sort for levels
                this.edges.forEach(edge => {{
                    const source = this.nodes[edge.source];
                    const target = this.nodes[edge.target];
                    
                    if (!levels[edge.source]) levels[edge.source] = 0;
                    levels[edge.target] = Math.max(levels[edge.target] || 0, levels[edge.source] + 1);
                }});
                
                // Position nodes by level
                const levelGroups = {{}};
                this.nodes.forEach((node, i) => {{
                    const level = levels[i] || 0;
                    if (!levelGroups[level]) levelGroups[level] = [];
                    levelGroups[level].push(node);
                }});
                
                Object.keys(levelGroups).forEach(level => {{
                    const nodesInLevel = levelGroups[level];
                    const y = 100 + parseInt(level) * 150;
                    const spacing = this.canvas.width / (nodesInLevel.length + 1);
                    
                    nodesInLevel.forEach((node, i) => {{
                        node.x = spacing * (i + 1);
                        node.y = y;
                    }});
                }});
            }}
            
            applyForceLayout() {{
                // Simple force-directed layout
                const iterations = 50;
                const k = 100; // Optimal distance
                const c = 0.1; // Damping
                
                for (let iter = 0; iter < iterations; iter++) {{
                    // Reset forces
                    this.nodes.forEach(node => {{
                        node.fx = 0;
                        node.fy = 0;
                    }});
                    
                    // Repulsive forces between all nodes
                    for (let i = 0; i < this.nodes.length; i++) {{
                        for (let j = i + 1; j < this.nodes.length; j++) {{
                            const dx = this.nodes[j].x - this.nodes[i].x;
                            const dy = this.nodes[j].y - this.nodes[i].y;
                            const distance = Math.sqrt(dx * dx + dy * dy);
                            
                            if (distance > 0) {{
                                const force = (k * k) / distance;
                                this.nodes[i].fx -= (dx / distance) * force;
                                this.nodes[i].fy -= (dy / distance) * force;
                                this.nodes[j].fx += (dx / distance) * force;
                                this.nodes[j].fy += (dy / distance) * force;
                            }}
                        }}
                    }}
                    
                    // Attractive forces for edges
                    this.edges.forEach(edge => {{
                        const source = this.nodes[edge.source];
                        const target = this.nodes[edge.target];
                        
                        const dx = target.x - source.x;
                        const dy = target.y - source.y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        
                        if (distance > 0) {{
                            const force = (distance * distance) / k;
                            source.fx += (dx / distance) * force;
                            source.fy += (dy / distance) * force;
                            target.fx -= (dx / distance) * force;
                            target.fy -= (dy / distance) * force;
                        }}
                    }});
                    
                    // Update positions
                    this.nodes.forEach(node => {{
                        node.x += node.fx * c;
                        node.y += node.fy * c;
                        
                        // Keep nodes within bounds
                        node.x = Math.max(50, Math.min(this.canvas.width - 50, node.x));
                        node.y = Math.max(50, Math.min(this.canvas.height - 50, node.y));
                    }});
                }}
            }}
            
            populateFilters() {{
                const categories = [...new Set(this.nodes.map(n => n.category))];
                const select = document.getElementById('categoryFilter');
                
                categories.forEach(category => {{
                    const option = document.createElement('option');
                    option.value = category;
                    option.textContent = category.charAt(0).toUpperCase() + category.slice(1);
                    select.appendChild(option);
                }});
                
                // Populate legend
                const legendItems = document.getElementById('legendItems');
                categories.forEach(category => {{
                    const item = document.createElement('div');
                    item.className = 'legend-item';
                    item.innerHTML = `
                        <div class="legend-color" style="background: ${{this.colors[category]}}"></div>
                        <span class="legend-label">${{category}} (${{this.nodes.filter(n => n.category === category).length}})</span>
                    `;
                    legendItems.appendChild(item);
                }});
            }}
            
            updateStats() {{
                document.getElementById('totalNodes').textContent = this.nodes.length;
                document.getElementById('totalEdges').textContent = this.edges.length;
                document.getElementById('visibleNodes').textContent = this.nodes.filter(n => n.visible !== false).length;
            }}
            
            updateZoomLevel() {{
                document.getElementById('zoomLevel').textContent = Math.round(this.zoom * 100) + '%';
            }}
            
            draw() {{
                // Clear canvas
                this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                
                // Apply transformations
                this.ctx.save();
                this.ctx.translate(this.offsetX, this.offsetY);
                this.ctx.scale(this.zoom, this.zoom);
                
                // Draw edges
                this.ctx.strokeStyle = 'rgba(160, 174, 192, 0.3)';
                this.ctx.lineWidth = 1 / this.zoom;
                
                this.edges.forEach(edge => {{
                    const source = this.nodes[edge.source];
                    const target = this.nodes[edge.target];
                    
                    if (source.visible !== false && target.visible !== false) {{
                        this.ctx.beginPath();
                        this.ctx.moveTo(source.x, source.y);
                        this.ctx.lineTo(target.x, target.y);
                        this.ctx.stroke();
                    }}
                }});
                
                // Draw nodes
                this.nodes.forEach(node => {{
                    if (node.visible !== false) {{
                        this.ctx.fillStyle = this.colors[node.category] || this.colors.other;
                        this.ctx.beginPath();
                        this.ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);
                        this.ctx.fill();
                        
                        // Draw node label
                        this.ctx.fillStyle = '#2d3748';
                        this.ctx.font = `${{12 / this.zoom}}px Arial`;
                        this.ctx.textAlign = 'center';
                        this.ctx.fillText(node.name, node.x, node.y + node.radius + 15 / this.zoom);
                    }}
                }});
                
                this.ctx.restore();
            }}
            
            animate() {{
                this.draw();
                requestAnimationFrame(() => this.animate());
            }}
        }}
        
        // Global functions
        let graphViewer;
        
        function zoomIn() {{
            graphViewer.zoom *= 1.2;
            graphViewer.zoom = Math.min(5, graphViewer.zoom);
            graphViewer.updateZoomLevel();
        }}
        
        function zoomOut() {{
            graphViewer.zoom *= 0.8;
            graphViewer.zoom = Math.max(0.1, graphViewer.zoom);
            graphViewer.updateZoomLevel();
        }}
        
        function fitToScreen() {{
            graphViewer.zoom = 1.0;
            graphViewer.offsetX = 0;
            graphViewer.offsetY = 0;
            graphViewer.updateZoomLevel();
        }}
        
        function resetView() {{
            fitToScreen();
            graphViewer.applyLayout('force');
        }}
        
        function toggleAnimation() {{
            graphViewer.animationRunning = !graphViewer.animationRunning;
        }}
        
        function exportGraph() {{
            const dataStr = JSON.stringify(graphViewer.data, null, 2);
            const dataBlob = new Blob([dataStr], {{type: 'application/json'}});
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'graph_data.json';
            link.click();
            URL.revokeObjectURL(url);
        }}
        
        // Initialize on load
        document.addEventListener('DOMContentLoaded', function() {{
            graphViewer = new GraphViewer('graphCanvas', window.graphData);
        }});
    </script>
</body>
</html>"""

        return html_template


def main():
    """Main function to generate graph viewer."""

    hybrid_path = Path("output_hybrid")
    if not hybrid_path.exists():
        print("❌ Hybrid export not found. Run hybrid export first.")
        return

    generator = GraphGenerator(hybrid_path)
    output_path = generator.generate_graph_viewer()

    print("\n🎉 Graph viewer ready!")
    print(f"Open {output_path} in your browser")
    print("Features: Zoom, Pan, Search, Filter, Export")


if __name__ == "__main__":
    main()
