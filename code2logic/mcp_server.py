"""
MCP (Model Context Protocol) Server for Code2Logic

Provides Code2Logic functionality as an MCP server for integration
with Claude Desktop and other MCP-compatible clients.

Usage:
    # Start server
    python -m code2logic.mcp_server

    # Or via CLI
    code2logic-mcp

Configuration for Claude Desktop (claude_desktop_config.json):
{
  "mcpServers": {
    "code2logic": {
      "command": "python",
      "args": ["-m", "code2logic.mcp_server"]
    }
  }
}
"""

import json
import sys

from . import __version__

# MCP protocol implementation
# Note: This is a simplified implementation. For production, use the official MCP SDK.


def handle_request(request: dict) -> dict:
    """Handle incoming MCP request."""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "0.1.0",
                "serverInfo": {"name": "code2logic", "version": __version__},
                "capabilities": {"tools": {}},
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "analyze_project",
                        "description": "Analyze a codebase and generate logical representation",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the project directory",
                                },
                                "format": {
                                    "type": "string",
                                    "enum": [
                                        "csv",
                                        "json",
                                        "yaml",
                                        "compact",
                                        "markdown",
                                    ],
                                    "default": "csv",
                                    "description": "Output format",
                                },
                                "detail": {
                                    "type": "string",
                                    "enum": ["minimal", "standard", "full"],
                                    "default": "standard",
                                    "description": "Detail level",
                                },
                            },
                            "required": ["path"],
                        },
                    },
                    {
                        "name": "find_duplicates",
                        "description": "Find duplicate functions in a codebase",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the project directory",
                                }
                            },
                            "required": ["path"],
                        },
                    },
                    {
                        "name": "compare_projects",
                        "description": "Compare two projects for similarities",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path1": {
                                    "type": "string",
                                    "description": "Path to first project",
                                },
                                "path2": {
                                    "type": "string",
                                    "description": "Path to second project",
                                },
                            },
                            "required": ["path1", "path2"],
                        },
                    },
                    {
                        "name": "suggest_refactoring",
                        "description": "Analyze project and suggest refactoring improvements",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the project directory",
                                }
                            },
                            "required": ["path"],
                        },
                    },
                ]
            },
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)},
            }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def call_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool and return result."""
    from .analyzer import ProjectAnalyzer
    from .generators import (
        CompactGenerator,
        CSVGenerator,
        JSONGenerator,
        MarkdownGenerator,
        YAMLGenerator,
    )

    if tool_name == "analyze_project":
        path = arguments.get("path")
        format_type = arguments.get("format", "csv")
        detail = arguments.get("detail", "standard")

        analyzer = ProjectAnalyzer(path)
        project = analyzer.analyze()

        generators = {
            "csv": CSVGenerator(),
            "json": JSONGenerator(),
            "yaml": YAMLGenerator(),
            "compact": CompactGenerator(),
            "markdown": MarkdownGenerator(),
        }

        gen = generators.get(format_type, CSVGenerator())

        if format_type in ("csv", "yaml"):
            return gen.generate(project, detail=detail)
        elif format_type == "json":
            return gen.generate(project, flat=True, detail=detail)
        elif format_type == "compact":
            return gen.generate(project)
        else:
            return gen.generate(project, detail)

    elif tool_name == "find_duplicates":
        path = arguments.get("path")

        analyzer = ProjectAnalyzer(path)
        project = analyzer.analyze()

        # Find duplicates by hash
        from collections import defaultdict

        hash_groups = defaultdict(list)

        for m in project.modules:
            for f in m.functions:
                sig = f"({','.join(f.params)})->{f.return_type or ''}"
                import hashlib

                h = hashlib.md5(f"{f.name}:{sig}".encode()).hexdigest()[:8]
                hash_groups[h].append(f"{m.path}::{f.name}")

            for c in m.classes:
                for method in c.methods:
                    sig = f"({','.join(method.params)})->{method.return_type or ''}"
                    import hashlib

                    h = hashlib.md5(f"{method.name}:{sig}".encode()).hexdigest()[:8]
                    hash_groups[h].append(f"{m.path}::{c.name}.{method.name}")

        duplicates = {h: paths for h, paths in hash_groups.items() if len(paths) > 1}

        result = ["# Duplicate Detection Results\n"]
        result.append(f"Total unique elements: {len(hash_groups)}")
        result.append(f"Duplicate groups: {len(duplicates)}\n")

        for h, paths in list(duplicates.items())[:20]:
            result.append(f"\n## Hash: {h}")
            for p in paths:
                result.append(f"  - {p}")

        return "\n".join(result)

    elif tool_name == "compare_projects":
        path1 = arguments.get("path1")
        path2 = arguments.get("path2")

        analyzer1 = ProjectAnalyzer(path1)
        analyzer2 = ProjectAnalyzer(path2)

        project1 = analyzer1.analyze()
        project2 = analyzer2.analyze()

        # Compare
        def get_hashes(project):
            hashes = {}
            for m in project.modules:
                for f in m.functions:
                    sig = f"({','.join(f.params)})->{f.return_type or ''}"
                    import hashlib

                    h = hashlib.md5(f"{f.name}:{sig}".encode()).hexdigest()[:8]
                    hashes[h] = f"{m.path}::{f.name}"
            return hashes

        h1 = get_hashes(project1)
        h2 = get_hashes(project2)

        common = set(h1.keys()) & set(h2.keys())
        only1 = set(h1.keys()) - set(h2.keys())
        only2 = set(h2.keys()) - set(h1.keys())

        result = ["# Project Comparison Results\n"]
        result.append(f"Project 1: {project1.name} ({project1.total_files} files)")
        result.append(f"Project 2: {project2.name} ({project2.total_files} files)\n")
        result.append(f"Identical elements: {len(common)}")
        result.append(f"Only in Project 1: {len(only1)}")
        result.append(f"Only in Project 2: {len(only2)}")

        if common:
            result.append("\n## Identical Elements (first 10)")
            for h in list(common)[:10]:
                result.append(f"  - {h1[h]} <-> {h2[h]}")

        return "\n".join(result)

    elif tool_name == "suggest_refactoring":
        path = arguments.get("path")

        analyzer = ProjectAnalyzer(path)
        project = analyzer.analyze()

        issues = []

        # Find high complexity (approximation based on lines)
        for m in project.modules:
            for f in m.functions:
                if f.lines > 50:
                    issues.append(
                        {
                            "type": "long_function",
                            "path": m.path,
                            "name": f.name,
                            "lines": f.lines,
                            "suggestion": "Consider breaking into smaller functions",
                        }
                    )

            if m.lines_code > 500:
                issues.append(
                    {
                        "type": "long_file",
                        "path": m.path,
                        "lines": m.lines_code,
                        "suggestion": "Consider splitting into multiple modules",
                    }
                )

        result = ["# Refactoring Suggestions\n"]
        result.append(f"Issues found: {len(issues)}\n")

        for issue in issues[:20]:
            result.append(f"\n## [{issue['type'].upper()}] {issue.get('path', '')}")
            if "name" in issue:
                result.append(f"Function: {issue['name']}")
            if "lines" in issue:
                result.append(f"Lines: {issue['lines']}")
            result.append(f"Suggestion: {issue['suggestion']}")

        return "\n".join(result)

    raise ValueError(f"Unknown tool: {tool_name}")


def run_server():
    """Run the MCP server."""
    print("Code2Logic MCP Server started", file=sys.stderr)

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line)
            response = handle_request(request)

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            print(f"JSON error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    run_server()
