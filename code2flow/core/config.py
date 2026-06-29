# Backward-compat configuration for the code2flow analysis API.
from __future__ import annotations

from dataclasses import dataclass, field


class FilterConfig:
    """File/function filtering configuration."""

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


@dataclass
class DepthConfig:
    """Limits on analysis depth."""

    max_cfg_depth: int = 3
    max_call_depth: int = 2


@dataclass
class PerformanceConfig:
    """Performance-related options."""

    fast_mode: bool = True
    enable_cache: bool = False
    cache_dir: str | None = None


@dataclass
class AnalysisConfig:
    """Top-level analysis configuration (the old code2flow ``Config``)."""

    depth: DepthConfig = field(default_factory=DepthConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)


# Backward-compat alias: the analysis configuration used to be called ``Config``.
Config = AnalysisConfig

FAST_CONFIG = AnalysisConfig(
    depth=DepthConfig(max_cfg_depth=3, max_call_depth=2),
    performance=PerformanceConfig(fast_mode=True),
    filters=FilterConfig(exclude_tests=True, skip_private=True),
)
