#!/usr/bin/env python3
"""
Generate index.html with embedded YAML data to avoid CORS issues.
"""

import yaml
import json
from pathlib import Path


def generate_index_html():
    """Generate index.html with embedded data."""

    print("🔄 Generating index.html with embedded data...")

    # Load index.yaml
    index_path = Path("output_hybrid/index.yaml")
    with open(index_path, "r") as f:
        index_data = yaml.safe_load(f)

    # Convert to JSON for embedding
    index_json = json.dumps(index_data, indent=2)

    # HTML template with embedded data
    html_template = (
        """<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hybrid Export - Code Analysis Tree Viewer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            text-align: center;
        }

        .header h1 {
            color: #4a5568;
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .header p {
            color: #718096;
            font-size: 1.1em;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-5px);
        }

        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }

        .stat-label {
            color: #718096;
            font-size: 0.9em;
        }

        .tree-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        }

        .search-box {
            margin-bottom: 20px;
        }

        .search-box input {
            width: 100%;
            padding: 12px 20px;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            font-size: 1em;
            transition: border-color 0.3s ease;
        }

        .search-box input:focus {
            outline: none;
            border-color: #667eea;
        }

        .tree {
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.6;
            max-height: 600px;
            overflow-y: auto;
        }

        .tree-node {
            margin: 2px 0;
            position: relative;
        }

        .tree-node.folder {
            font-weight: bold;
            color: #4a5568;
        }

        .tree-node.file {
            color: #718096;
        }

        .tree-node.file:hover {
            background: #f7fafc;
            border-radius: 4px;
        }

        .tree-node a {
            text-decoration: none;
            color: inherit;
            display: block;
            padding: 2px 8px;
            border-radius: 4px;
            transition: all 0.3s ease;
        }

        .tree-node a:hover {
            background: #edf2f7;
            color: #667eea;
            transform: translateX(5px);
        }

        .tree-toggle {
            cursor: pointer;
            user-select: none;
            margin-right: 5px;
            color: #a0aec0;
            transition: color 0.3s ease;
        }

        .tree-toggle:hover {
            color: #667eea;
        }

        .tree-toggle.collapsed::before {
            content: '▶';
        }

        .tree-toggle.expanded::before {
            content: '▼';
        }

        .tree-children {
            margin-left: 20px;
            border-left: 1px solid #e2e8f0;
            padding-left: 10px;
        }

        .tree-children.collapsed {
            display: none;
        }

        .highlight {
            background: #fef5e7;
            border-radius: 4px;
            padding: 2px 4px;
        }

        .controls {
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            background: #667eea;
            color: white;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9em;
        }

        .btn:hover {
            background: #5a67d8;
            transform: translateY(-2px);
        }

        .btn.secondary {
            background: #e2e8f0;
            color: #4a5568;
        }

        .btn.secondary:hover {
            background: #cbd5e0;
        }

        .file-info {
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            max-width: 300px;
            display: none;
            z-index: 1000;
        }

        .file-info.show {
            display: block;
        }

        .file-info h3 {
            color: #4a5568;
            margin-bottom: 10px;
        }

        .file-info p {
            color: #718096;
            font-size: 0.9em;
            margin-bottom: 5px;
        }

        .close-info {
            position: absolute;
            top: 10px;
            right: 10px;
            cursor: pointer;
            color: #a0aec0;
            font-size: 1.2em;
        }

        .close-info:hover {
            color: #4a5568;
        }

        .error {
            background: #fed7d7;
            color: #c53030;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }

            .header h1 {
                font-size: 2em;
            }

            .stats {
                grid-template-columns: 1fr;
            }

            .file-info {
                position: static;
                max-width: 100%;
                margin: 20px 0;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌳 Hybrid Export Tree Viewer</h1>
            <p>Interactive code analysis tree explorer with 858 files</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-number" id="totalFiles">858</div>
                <div class="stat-label">Total Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="consolidatedFiles">404</div>
                <div class="stat-label">Consolidated</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="orphanFiles">453</div>
                <div class="stat-label">Orphans</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="totalFunctions">3,649</div>
                <div class="stat-label">Functions</div>
            </div>
        </div>

        <div class="tree-container">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 Search files... (type to filter)">
            </div>

            <div class="controls">
                <button class="btn" onclick="expandAll()">Expand All</button>
                <button class="btn" onclick="collapseAll()">Collapse All</button>
                <button class="btn secondary" onclick="showConsolidatedOnly()">Consolidated Only</button>
                <button class="btn secondary" onclick="showOrphansOnly()">Orphans Only</button>
                <button class="btn secondary" onclick="showAll()">Show All</button>
            </div>

            <div id="treeContainer" class="tree">
                <div class="loading">🔄 Loading file tree...</div>
            </div>
        </div>
    </div>

    <div class="file-info" id="fileInfo">
        <span class="close-info" onclick="closeFileInfo()">×</span>
        <h3 id="fileInfoTitle">File Information</h3>
        <p id="fileInfoPath"></p>
        <p id="fileInfoSize"></p>
        <p id="fileInfoType"></p>
        <p id="fileInfoCount"></p>
    </div>

    <script>
        // Embedded data to avoid CORS issues
        window.indexData = """
        + index_json
        + """;

        // Global variables
        let treeData = null;
        let currentFilter = 'all';

        // Initialize the application
        document.addEventListener('DOMContentLoaded', function() {
            loadTreeData();
            setupSearch();
        });

        // Load tree data from embedded script
        function loadTreeData() {
            try {
                treeData = window.indexData;
                
                // Build tree structure
                const treeStructure = buildTreeStructure(treeData);
                renderTree(treeStructure);
                
                // Update stats
                updateStats(treeData);
                
            } catch (error) {
                console.error('Error loading tree data:', error);
                document.getElementById('treeContainer').innerHTML = 
                    '<div class="error">❌ Error loading tree data.</div>';
            }
        }

        // Build tree structure from file list
        function buildTreeStructure(data) {
            const tree = {
                name: 'output_hybrid',
                type: 'folder',
                children: []
            };

            // Add consolidated folder
            const consolidated = {
                name: 'consolidated',
                type: 'folder',
                children: [
                    { name: 'summary.yaml', type: 'file', path: 'consolidated/summary.yaml' }
                ]
            };

            // Add consolidated functions from generated_files
            if (data.generated_files) {
                data.generated_files.forEach(file => {
                    if (file.startsWith('consolidated/functions_')) {
                        consolidated.children.push({
                            name: file.replace('consolidated/', ''),
                            type: 'file',
                            path: file
                        });
                    }
                });
            }

            // Add orphans folder
            const orphans = {
                name: 'orphans',
                type: 'folder',
                children: [
                    { name: 'summary.yaml', type: 'file', path: 'orphans/summary.yaml' }
                ]
            };

            // Add orphan functions and nodes from generated_files
            if (data.generated_files) {
                data.generated_files.forEach(file => {
                    if (file.startsWith('orphans/')) {
                        orphans.children.push({
                            name: file.replace('orphans/', ''),
                            type: 'file',
                            path: file
                        });
                    }
                });
            }

            tree.children.push(consolidated, orphans);
            return tree;
        }

        // Render tree
        function renderTree(treeData) {
            const container = document.getElementById('treeContainer');
            container.innerHTML = renderTreeNode(treeData, 0);
            setupTreeToggles();
        }

        // Render tree node recursively
        function renderTreeNode(node, level) {
            const indent = '  '.repeat(level);
            const isFolder = node.type === 'folder';
            const hasChildren = node.children && node.children.length > 0;
            
            let html = '';
            
            if (isFolder) {
                const toggleClass = hasChildren ? 'tree-toggle expanded' : '';
                const icon = hasChildren ? '📁' : '📄';
                
                html += `
                    <div class="tree-node folder" data-level="${level}">
                        ${indent}<span class="${toggleClass}"></span>${icon} ${node.name}
                    </div>
                `;
                
                if (hasChildren) {
                    html += '<div class="tree-children">';
                    node.children.forEach(child => {
                        html += renderTreeNode(child, level + 1);
                    });
                    html += '</div>';
                }
            } else {
                const icon = getNodeIcon(node.name);
                const category = getCategory(node.path);
                
                html += `
                    <div class="tree-node file" data-level="${level}" data-category="${category}">
                        ${indent}${icon} <a href="${node.path}" onclick="showFileInfo(event, '${node.path}', '${node.name}', '${category}')">${node.name}</a>
                    </div>
                `;
            }
            
            return html;
        }

        // Get node icon based on file name
        function getNodeIcon(fileName) {
            if (fileName.includes('summary')) return '📊';
            if (fileName.includes('functions')) return '⚙️';
            if (fileName.includes('nodes')) return '🔗';
            if (fileName.includes('index')) return '📋';
            return '📄';
        }

        // Get category from file path
        function getCategory(path) {
            if (path.includes('consolidated')) return 'consolidated';
            if (path.includes('orphans')) return 'orphans';
            return 'other';
        }

        // Setup tree toggles
        function setupTreeToggles() {
            document.querySelectorAll('.tree-toggle').forEach(toggle => {
                toggle.addEventListener('click', function(e) {
                    e.stopPropagation();
                    toggleFolder(this);
                });
            });
        }

        // Toggle folder
        function toggleFolder(toggle) {
            const isExpanded = toggle.classList.contains('expanded');
            const children = toggle.parentElement.nextElementSibling;
            
            if (isExpanded) {
                toggle.classList.remove('expanded');
                toggle.classList.add('collapsed');
                if (children) children.classList.add('collapsed');
            } else {
                toggle.classList.remove('collapsed');
                toggle.classList.add('expanded');
                if (children) children.classList.remove('collapsed');
            }
        }

        // Expand all folders
        function expandAll() {
            document.querySelectorAll('.tree-toggle.collapsed').forEach(toggle => {
                toggleFolder(toggle);
            });
        }

        // Collapse all folders
        function collapseAll() {
            document.querySelectorAll('.tree-toggle.expanded').forEach(toggle => {
                toggleFolder(toggle);
            });
        }

        // Filter functions
        function showConsolidatedOnly() {
            currentFilter = 'consolidated';
            applyFilter();
        }

        function showOrphansOnly() {
            currentFilter = 'orphans';
            applyFilter();
        }

        function showAll() {
            currentFilter = 'all';
            applyFilter();
        }

        function applyFilter() {
            document.querySelectorAll('.tree-node.file').forEach(node => {
                const category = node.dataset.category;
                if (currentFilter === 'all' || category === currentFilter) {
                    node.style.display = 'block';
                } else {
                    node.style.display = 'none';
                }
            });
        }

        // Setup search
        function setupSearch() {
            const searchInput = document.getElementById('searchInput');
            searchInput.addEventListener('input', function(e) {
                const query = e.target.value.toLowerCase();
                searchFiles(query);
            });
        }

        // Search files
        function searchFiles(query) {
            if (query === '') {
                clearSearch();
                return;
            }

            // Expand all folders to show search results
            expandAll();

            document.querySelectorAll('.tree-node.file').forEach(node => {
                const fileName = node.textContent.toLowerCase();
                const link = node.querySelector('a');
                
                if (fileName.includes(query)) {
                    node.style.display = 'block';
                    if (link) {
                        link.innerHTML = highlightText(link.textContent, query);
                    }
                } else {
                    node.style.display = 'none';
                }
            });
        }

        // Clear search
        function clearSearch() {
            document.querySelectorAll('.tree-node.file').forEach(node => {
                node.style.display = 'block';
                const link = node.querySelector('a');
                if (link) {
                    link.innerHTML = link.textContent;
                }
            });
            applyFilter();
        }

        // Highlight search text
        function highlightText(text, query) {
            const regex = new RegExp(`(${query})`, 'gi');
            return text.replace(regex, '<span class="highlight">$1</span>');
        }

        // Show file information
        function showFileInfo(event, path, name, category) {
            event.preventDefault();
            
            const fileInfo = document.getElementById('fileInfo');
            const title = document.getElementById('fileInfoTitle');
            const pathEl = document.getElementById('fileInfoPath');
            const typeEl = document.getElementById('fileInfoType');
            const countEl = document.getElementById('fileInfoCount');
            
            title.textContent = name;
            pathEl.textContent = `Path: ${path}`;
            typeEl.textContent = `Category: ${category}`;
            
            // Estimate file size and count based on file name
            let estimatedSize = 'Unknown';
            let estimatedCount = 'Unknown';
            
            if (name.includes('summary')) {
                estimatedSize = '~5KB';
                estimatedCount = 'Summary data';
            } else if (name.includes('functions')) {
                estimatedSize = '~10-50KB';
                estimatedCount = 'Multiple functions';
            } else if (name.includes('nodes')) {
                estimatedSize = '~20-100KB';
                estimatedCount = 'Multiple nodes';
            }
            
            document.getElementById('fileInfoSize').textContent = `Estimated size: ${estimatedSize}`;
            countEl.textContent = `Content: ${estimatedCount}`;
            
            fileInfo.classList.add('show');
        }

        // Close file information
        function closeFileInfo() {
            document.getElementById('fileInfo').classList.remove('show');
        }

        // Update statistics
        function updateStats(data) {
            if (data.total_stats) {
                document.getElementById('totalFunctions').textContent = 
                    data.total_stats.functions ? data.total_stats.functions.toLocaleString() : '3,649';
            }
            
            if (data.structure) {
                const consolidatedStats = data.structure.consolidated?.stats || {};
                const orphanStats = data.structure.orphans?.stats || {};
                
                document.getElementById('consolidatedFiles').textContent = 
                    (consolidatedStats.functions || 3375).toLocaleString();
                document.getElementById('orphanFiles').textContent = 
                    (orphanStats.functions || 274).toLocaleString();
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'f':
                        e.preventDefault();
                        document.getElementById('searchInput').focus();
                        break;
                    case 'e':
                        e.preventDefault();
                        expandAll();
                        break;
                    case 'w':
                        e.preventDefault();
                        collapseAll();
                        break;
                }
            }
            
            if (e.key === 'Escape') {
                closeFileInfo();
                document.getElementById('searchInput').value = '';
                clearSearch();
            }
        });
    </script>
</body>
</html>"""
    )

    # Write the complete HTML file
    output_path = Path("output_hybrid/index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)

    print("✓ Generated index.html with embedded data")
    print(f"  • File: {output_path}")
    print(f"  • Size: {output_path.stat().st_size / 1024:.1f}K")
    print("  • CORS issue resolved")
    print("  • Ready to open in browser")

    return output_path


if __name__ == "__main__":
    generate_index_html()
