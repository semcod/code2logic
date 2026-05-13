"""External integrations.

Re-exports from parent package for backward compatibility.
"""

from ..mcp_server import call_tool, handle_request, run_server

__all__ = ["handle_request", "call_tool", "run_server"]
