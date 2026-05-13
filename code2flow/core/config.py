# Backward-compat shim: code2flow.core.config → code2logic.config
from __future__ import annotations
from code2logic.config import Config  # noqa: F401

FAST_CONFIG = Config()


class FilterConfig:
    """Stub for file/function filtering configuration."""

    def __init__(
        self,
        exclude_tests: bool = False,
        exclude_patterns: list[str] | None = None,
        skip_private: bool = False,
        skip_properties: bool = False,
        min_function_lines: int = 0,
    ) -> None:
        self.exclude_tests = exclude_tests
        self.exclude_patterns = exclude_patterns or []
        self.skip_private = skip_private
        self.skip_properties = skip_properties
        self.min_function_lines = min_function_lines
