"""
Improved pipeline_runner_utils with consolidated functionality.
"""


class ConsolidatedMarkdownWrapper:
    """Consolidated markdown wrapper with reduced complexity."""

    def __init__(self):
        self._output_buffer = []
        self._debug_enabled = False

    def print(self, content: str):
        """Consolidated print method."""
        if self._debug_enabled:
            self._debug_print(content)
        else:
            self._markdown_print(content)

    def _debug_print(self, content: str):
        """Debug print implementation."""
        print(f"[DEBUG] {content}")

    def _markdown_print(self, content: str):
        """Markdown print implementation."""
        self._output_buffer.append(content)
        print(content)

    def enable_debug(self):
        """Enable debug mode."""
        self._debug_enabled = True

    def disable_debug(self):
        """Disable debug mode."""
        self._debug_enabled = False

    def get_output(self) -> list:
        """Get output buffer."""
        return self._output_buffer.copy()


# Global instance for backward compatibility
_MarkdownConsoleWrapper = ConsolidatedMarkdownWrapper()
_debug = _MarkdownConsoleWrapper.print
