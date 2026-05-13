"""
Base classes and mixins for code2logic.

Provides common functionality:
- VerboseMixin for logging
- BaseParser for parsers
- BaseGenerator for generators
"""

import logging


class VerboseMixin:
    """Mixin providing verbose logging functionality."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._logger = logging.getLogger(self.__class__.__name__)
        if verbose:
            self._logger.setLevel(logging.DEBUG)

    def log(self, msg: str, level: str = "info"):
        """Log message if verbose mode enabled."""
        if self.verbose:
            log_func = getattr(self._logger, level, self._logger.info)
            log_func(f"[{self.__class__.__name__}] {msg}")

    def debug(self, msg: str):
        """Log debug message."""
        self.log(msg, "debug")

    def info(self, msg: str):
        """Log info message."""
        self.log(msg, "info")

    def warn(self, msg: str):
        """Log warning message."""
        self.log(msg, "warning")

    def error(self, msg: str):
        """Log error message."""
        self.log(msg, "error")


class BaseParser(VerboseMixin):
    """Base class for code parsers."""

    def __init__(self, verbose: bool = False):
        super().__init__(verbose)

    def parse(self, content: str, language: str = None):
        """Parse source code content."""
        raise NotImplementedError

    def parse_file(self, path: str):
        """Parse source file."""
        raise NotImplementedError


class BaseGenerator(VerboseMixin):
    """Base class for output generators."""

    def __init__(self, verbose: bool = False):
        super().__init__(verbose)

    def generate(self, project, detail: str = "full") -> str:
        """Generate output from project analysis."""
        raise NotImplementedError
