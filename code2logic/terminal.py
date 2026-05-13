"""
Terminal Renderer - Colorized Markdown Output in Shell.

Renders markdown codeblocks with ANSI colors in terminal.
Provides syntax highlighting for YAML, JSON, Python, Bash, Markdown.

Based on: /home/tom/github/wronai/contract/src/python/reclapp/evolution/shell_renderer.py

Usage:
    from code2logic.terminal import render, ShellRenderer

    render.heading(2, "Benchmark Results")
    render.codeblock("yaml", "score: 95.5\\nformat: yaml")
    render.success("All tests passed")
    render.progress(5, 10, "Processing files")

@version 1.0.0
"""

import os
import re
import sys
from typing import Any, List, Literal, Optional

# ANSI color codes
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    # Foreground
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    # Bright foreground
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    # Background
    "bg_black": "\033[40m",
    "bg_red": "\033[41m",
    "bg_green": "\033[42m",
    "bg_yellow": "\033[43m",
    "bg_blue": "\033[44m",
    "bg_gray": "\033[100m",
}

Language = Literal[
    "yaml",
    "yml",
    "json",
    "python",
    "py",
    "bash",
    "sh",
    "typescript",
    "ts",
    "javascript",
    "js",
    "markdown",
    "md",
    "log",
    "text",
    "txt",
    "gherkin",
    "feature",
]


class ShellRenderer:
    """
    Renders colorized markdown output in terminal.

    Supports syntax highlighting for:
    - YAML/YML
    - JSON
    - Python
    - Bash/Shell
    - TypeScript/JavaScript
    - Markdown
    - Gherkin/Feature
    - Log messages

    Color scheme:
    - cyan:    Keys, headers, identifiers
    - green:   String values, success, commands
    - magenta: Numbers, keywords
    - yellow:  Booleans, warnings
    - gray:    Comments, dim text
    - red:     Errors
    - blue:    Links

    Example:
        renderer = ShellRenderer()
        renderer.heading(2, "Status")
        renderer.codeblock("yaml", "status: ok\\ncount: 42")
        renderer.success("Done!")
    """

    def __init__(self, use_colors: bool = True, verbose: bool = True):
        self.verbose = verbose
        # Detect if terminal supports colors
        self.use_colors = use_colors and self._supports_colors()
        self.log_buffer: List[str] = []
        self.log_enabled = False

    def _supports_colors(self) -> bool:
        """Check if terminal supports ANSI colors."""
        # Check for NO_COLOR env var (standard)
        if os.environ.get("NO_COLOR"):
            return False
        # Check for FORCE_COLOR
        if os.environ.get("FORCE_COLOR"):
            return True
        # Check if stdout is a TTY
        if not hasattr(sys.stdout, "isatty"):
            return False
        return sys.stdout.isatty()

    def enable_log(self) -> None:
        """Enable log buffering for markdown export."""
        self.log_enabled = True
        self.log_buffer = []

    def get_log(self) -> str:
        """Get buffered log as clean markdown (no ANSI codes)."""
        return "\n".join(self.log_buffer)

    def clear_log(self) -> None:
        """Clear log buffer."""
        self.log_buffer = []

    def _log(self, text: str) -> None:
        """Log a line (strips ANSI codes for markdown)."""
        if not self.verbose:
            return
        print(text)
        if self.log_enabled:
            # Strip ANSI codes for clean markdown
            clean = re.sub(r"\033\[[0-9;]*m", "", text)
            self.log_buffer.append(clean)

    def _c(self, color: str, text: str) -> str:
        """Apply color to text."""
        if not self.use_colors:
            return text
        code = COLORS.get(color, "")
        return f"{code}{text}{COLORS['reset']}"

    # =========================================================================
    # MARKDOWN ELEMENTS
    # =========================================================================

    def heading(self, level: int, text: str) -> None:
        """Print a markdown heading."""
        prefix = "#" * level
        self._log(f"\n{self._c('bold', self._c('cyan', f'{prefix} {text}'))}\n")

    def codeblock(self, language: Language, content: str) -> None:
        """Print a syntax-highlighted code block."""
        border = self._c("gray", f"```{language}")
        border_end = self._c("gray", "```")

        self._log("")
        self._log(border)

        for line in content.split("\n"):
            highlighted = self._highlight_line(line, language)
            self._log(highlighted)

        self._log(border_end)
        self._log("")

    def render_markdown(self, text: str) -> None:
        """Render full markdown text with syntax highlighting."""
        lines = text.split("\n")
        in_fence = False
        fence = "```"
        lang = "text"
        buf: List[str] = []

        for line in lines:
            trimmed = line.rstrip()

            # Check for fence markers
            match = re.match(r"^(`{3,})(.*)$", trimmed)

            if not in_fence:
                if match:
                    in_fence = True
                    fence = match.group(1)
                    lang = match.group(2).strip() or "text"
                    buf = []
                else:
                    # Regular markdown line
                    self._log(self._highlight_markdown(line))
            else:
                if trimmed.strip() == fence:
                    # End of code block
                    self.codeblock(lang, "\n".join(buf))
                    in_fence = False
                    fence = "```"
                    lang = "text"
                    buf = []
                else:
                    buf.append(line)

        # Flush remaining buffer
        if buf:
            self.codeblock(lang, "\n".join(buf))

    # =========================================================================
    # STATUS MESSAGES
    # =========================================================================

    def success(self, message: str) -> None:
        """Print success message."""
        self._log(f"{self._c('green', '✅')} {self._c('green', message)}")

    def error(self, message: str) -> None:
        """Print error message."""
        self._log(f"{self._c('red', '❌')} {self._c('red', message)}")

    def warning(self, message: str) -> None:
        """Print warning message."""
        self._log(f"{self._c('yellow', '⚠️')} {self._c('yellow', message)}")

    def info(self, message: str) -> None:
        """Print info message."""
        self._log(f"{self._c('cyan', 'ℹ️')} {self._c('cyan', message)}")

    def status(
        self,
        icon: str,
        message: str,
        type: Literal["info", "success", "warning", "error"] = "info",
    ) -> None:
        """Print status message with icon."""
        color_map = {
            "info": "blue",
            "success": "green",
            "warning": "yellow",
            "error": "red",
        }
        self._log(f"{icon} {self._c(color_map[type], message)}")

    # =========================================================================
    # FORMATTING
    # =========================================================================

    def kv(self, key: str, value: Any) -> None:
        """Print key-value pair."""
        self._log(f"  {self._c('cyan', key)}: {self._c('white', str(value))}")

    def progress(self, done: int, total: int, label: str = "") -> None:
        """Print progress bar."""
        pct = int((done / total) * 100) if total > 0 else 0
        filled = pct // 5
        bar = "█" * filled + "░" * (20 - filled)
        label_str = f" {label}" if label else ""
        self._log(
            f"{self._c('gray', '[')} {self._c('green', bar)} {self._c('gray', ']')} "
            f"{self._c('cyan', f'{pct}%')}{label_str}"
        )

    def separator(self, char: str = "─", width: int = 60) -> None:
        """Print separator line."""
        self._log(self._c("gray", char * width))

    def table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        widths: Optional[List[int]] = None,
    ) -> None:
        """Print a simple table."""
        if not widths:
            widths = [
                max(len(str(h)), max(len(str(r[i])) for r in rows) if rows else 0) + 2
                for i, h in enumerate(headers)
            ]

        # Header
        header_line = "".join(
            self._c("cyan", str(h).ljust(w)) for h, w in zip(headers, widths)
        )
        self._log(header_line)
        self._log(self._c("gray", "-" * sum(widths)))

        # Rows
        for row in rows:
            row_line = "".join(str(v).ljust(w) for v, w in zip(row, widths))
            self._log(row_line)

    def task(
        self,
        name: str,
        status: Literal["pending", "running", "done", "failed"],
        duration: Optional[float] = None,
    ) -> None:
        """Print task status."""
        icons = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}
        colors = {
            "pending": "gray",
            "running": "yellow",
            "done": "green",
            "failed": "red",
        }

        duration_str = f" ({duration:.1f}s)" if duration is not None else ""
        self._log(
            f"{icons[status]} {self._c(colors[status], name)}"
            f"{self._c('gray', duration_str)}"
        )

    def inline(self, text: str) -> str:
        """Return inline code styled text."""
        return self._c("cyan", text)

    def print(self, text: str, color: Optional[str] = None) -> None:
        """Print raw text with optional color."""
        self._log(self._c(color, text) if color else text)

    def newline(self) -> None:
        """Print empty line."""
        self._log("")

    # =========================================================================
    # SYNTAX HIGHLIGHTING
    # =========================================================================

    def _highlight_line(self, line: str, language: str) -> str:
        """Apply syntax highlighting to a line."""
        lang = language.lower()

        if lang in ("yaml", "yml"):
            return self._highlight_yaml(line)
        elif lang == "json":
            return self._highlight_json(line)
        elif lang in ("python", "py"):
            return self._highlight_python(line)
        elif lang in ("bash", "sh", "shell"):
            return self._highlight_bash(line)
        elif lang in ("typescript", "ts", "javascript", "js"):
            return self._highlight_js(line)
        elif lang in ("gherkin", "feature"):
            return self._highlight_gherkin(line)
        elif lang in ("log", "text", "txt"):
            return self._highlight_log(line)
        elif lang in ("markdown", "md"):
            return self._highlight_markdown(line)
        else:
            return self._c("white", line)

    def _highlight_yaml(self, line: str) -> str:
        """Highlight YAML syntax."""
        # Comments
        if line.strip().startswith("#"):
            return self._c("gray", line)

        # Key: value
        match = re.match(r"^(\s*)([^:]+)(:)(.*)$", line)
        if match:
            indent, key, colon, value = match.groups()

            # Color value based on type
            trimmed = value.strip()
            if trimmed.isdigit() or re.match(r"^-?\d+\.?\d*$", trimmed):
                value_colored = self._c("magenta", value)
            elif trimmed.lower() in ("true", "false", "yes", "no", "null", "none", "~"):
                value_colored = self._c("yellow", value)
            elif trimmed.startswith('"') or trimmed.startswith("'"):
                value_colored = self._c("green", value)
            elif trimmed:
                value_colored = self._c("green", value)
            else:
                value_colored = value

            return f"{indent}{self._c('cyan', key)}{colon}{value_colored}"

        # List item
        if line.strip().startswith("-"):
            match = re.match(r"^(\s*)(-)(.*)$", line)
            if match:
                indent, dash, rest = match.groups()
                return f"{indent}{self._c('white', dash)}{self._c('green', rest)}"

        return line

    def _highlight_json(self, line: str) -> str:
        """Highlight JSON syntax."""
        result = line

        # Keys
        def color_key(m):
            return self._c("cyan", '"' + m.group(1) + '"') + ": "

        result = re.sub(r'"([^"]+)"\s*:', color_key, result)

        # String values
        def color_str(m):
            return ": " + self._c("green", '"' + m.group(1) + '"')

        result = re.sub(r':\s*"([^"]*)"', color_str, result)

        # Numbers
        def color_num(m):
            return ": " + self._c("magenta", m.group(1))

        result = re.sub(r":\s*(-?\d+\.?\d*)", color_num, result)

        # Booleans/null
        def color_bool(m):
            return ": " + self._c("yellow", m.group(1))

        result = re.sub(r":\s*(true|false|null)", color_bool, result)

        return result

    def _highlight_python(self, line: str) -> str:
        """Highlight Python syntax."""
        # Comments
        if line.strip().startswith("#"):
            return self._c("gray", line)

        result = line

        # Keywords
        keywords = [
            "def",
            "class",
            "import",
            "from",
            "return",
            "if",
            "elif",
            "else",
            "for",
            "while",
            "try",
            "except",
            "finally",
            "with",
            "as",
            "yield",
            "async",
            "await",
            "lambda",
            "pass",
            "break",
            "continue",
            "raise",
            "True",
            "False",
            "None",
            "and",
            "or",
            "not",
            "in",
            "is",
        ]
        for kw in keywords:
            result = re.sub(rf"\b{kw}\b", self._c("magenta", kw), result)

        # Decorators
        result = re.sub(r"(@\w+)", self._c("yellow", r"\1"), result)

        # Strings
        result = re.sub(
            r'(["\'])(?:(?!\1).)*\1', lambda m: self._c("green", m.group(0)), result
        )

        return result

    def _highlight_bash(self, line: str) -> str:
        """Highlight Bash syntax."""
        # Comments
        if line.strip().startswith("#"):
            return self._c("gray", line)

        # Commands at start of line
        commands = [
            "cd",
            "npm",
            "node",
            "python",
            "pip",
            "git",
            "docker",
            "code2logic",
            "pytest",
            "make",
            "echo",
            "export",
            "source",
        ]
        for cmd in commands:
            if line.strip().startswith(cmd):
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    return f"{self._c('green', parts[0])} {parts[1]}"
                return self._c("green", line)

        return line

    def _highlight_js(self, line: str) -> str:
        """Highlight JavaScript/TypeScript syntax."""
        # Comments
        if line.strip().startswith("//"):
            return self._c("gray", line)

        result = line

        # Keywords
        keywords = [
            "const",
            "let",
            "var",
            "function",
            "async",
            "await",
            "return",
            "if",
            "else",
            "for",
            "while",
            "import",
            "export",
            "from",
            "class",
            "interface",
            "type",
            "extends",
            "implements",
        ]
        for kw in keywords:
            result = re.sub(rf"\b{kw}\b", self._c("magenta", kw), result)

        # Strings
        result = re.sub(
            r'(["\'])(?:(?!\1).)*\1', lambda m: self._c("green", m.group(0)), result
        )

        return result

    def _highlight_gherkin(self, line: str) -> str:
        """Highlight Gherkin/BDD syntax."""
        trimmed = line.strip()

        # Keywords
        if trimmed.startswith("Feature:"):
            return self._c("cyan", line)
        if trimmed.startswith("Scenario:") or trimmed.startswith("Scenario Outline:"):
            return self._c("bright_cyan", line)
        if trimmed.startswith("Background:"):
            return self._c("cyan", line)
        if trimmed.startswith("Given "):
            return self._c("blue", line)
        if trimmed.startswith("When "):
            return self._c("yellow", line)
        if trimmed.startswith("Then "):
            return self._c("green", line)
        if trimmed.startswith("And ") or trimmed.startswith("But "):
            return self._c("gray", line)
        if trimmed.startswith("@"):
            return self._c("magenta", line)
        if trimmed.startswith("#"):
            return self._c("gray", line)

        return line

    def _highlight_log(self, line: str) -> str:
        """Highlight log messages."""
        if "✅" in line or "success" in line.lower():
            return self._c("green", line)
        if "❌" in line or "error" in line.lower() or "fail" in line.lower():
            return self._c("red", line)
        if "⚠️" in line or "warn" in line.lower():
            return self._c("yellow", line)
        if "ℹ️" in line or "info" in line.lower():
            return self._c("cyan", line)
        if line.strip().startswith("→"):
            return self._c("gray", line)
        if "📊" in line:
            return self._c("magenta", line)
        if "🚀" in line:
            return self._c("green", line)
        if "📦" in line or "💬" in line:
            return self._c("cyan", line)

        return self._c("white", line)

    def _highlight_markdown(self, line: str) -> str:
        """Highlight Markdown syntax."""
        # Headers
        if re.match(r"^#{1,6}\s", line):
            return self._c("cyan", line)
        # Bold
        if "**" in line:
            line = re.sub(r"\*\*([^*]+)\*\*", self._c("bold", r"\1"), line)
        # Links
        if "[" in line:
            line = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                lambda m: (
                    f"{self._c('blue', f'[{m.group(1)}]')}({self._c('gray', m.group(2))})"
                ),
                line,
            )
        # Inline code
        if "`" in line:
            line = re.sub(
                r"`([^`]+)`", lambda m: self._c("cyan", f"`{m.group(1)}`"), line
            )

        return line

    def save_log(self, filepath: str) -> None:
        """Save log buffer to file as markdown."""
        import os

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(self.get_log())


# =============================================================================
# SINGLETON & CONVENIENCE API
# =============================================================================

_renderer: Optional[ShellRenderer] = None


def get_renderer(use_colors: bool = True, verbose: bool = True) -> ShellRenderer:
    """Get or create the global renderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = ShellRenderer(use_colors=use_colors, verbose=verbose)
    return _renderer


def set_renderer(renderer: ShellRenderer) -> None:
    """Set the global renderer instance."""
    global _renderer
    _renderer = renderer


class RenderAPI:
    """Convenience API for terminal rendering."""

    @staticmethod
    def heading(level: int, text: str) -> None:
        get_renderer().heading(level, text)

    @staticmethod
    def code(lang: Language, content: str) -> None:
        get_renderer().codeblock(lang, content)

    @staticmethod
    def codeblock(lang: Language, content: str) -> None:
        get_renderer().codeblock(lang, content)

    @staticmethod
    def markdown(text: str) -> None:
        get_renderer().render_markdown(text)

    @staticmethod
    def success(message: str) -> None:
        get_renderer().success(message)

    @staticmethod
    def error(message: str) -> None:
        get_renderer().error(message)

    @staticmethod
    def warning(message: str) -> None:
        get_renderer().warning(message)

    @staticmethod
    def info(message: str) -> None:
        get_renderer().info(message)

    @staticmethod
    def status(
        icon: str,
        message: str,
        type: Literal["info", "success", "warning", "error"] = "info",
    ) -> None:
        get_renderer().status(icon, message, type)

    @staticmethod
    def kv(key: str, value: Any) -> None:
        get_renderer().kv(key, value)

    @staticmethod
    def progress(done: int, total: int, label: str = "") -> None:
        get_renderer().progress(done, total, label)

    @staticmethod
    def separator(char: str = "─", width: int = 60) -> None:
        get_renderer().separator(char, width)

    @staticmethod
    def table(
        headers: List[str], rows: List[List[Any]], widths: Optional[List[int]] = None
    ) -> None:
        get_renderer().table(headers, rows, widths)

    @staticmethod
    def task(
        name: str,
        status: Literal["pending", "running", "done", "failed"],
        duration: Optional[float] = None,
    ) -> None:
        get_renderer().task(name, status, duration)

    @staticmethod
    def inline(text: str) -> str:
        return get_renderer().inline(text)

    @staticmethod
    def print(text: str, color: Optional[str] = None) -> None:
        get_renderer().print(text, color)

    @staticmethod
    def newline() -> None:
        get_renderer().newline()


# Global convenience instance
render = RenderAPI()
