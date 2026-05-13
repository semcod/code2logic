# Backward-compat wrappers for old code2flow API
from __future__ import annotations
from typing import Any
from code2logic import ProjectAnalyzer as _ProjectAnalyzer
from code2flow.core.config import Config, FilterConfig  # noqa: F401


class _AnalysisResultWrapper:
    """Wraps code2logic analysis result to expose old code2flow methods."""

    def __init__(self, result: Any, path: str) -> None:
        self._result = result
        self._path = path
        files_processed = getattr(result, "total_files", 0)
        self.stats: dict = {"files_processed": files_processed}

    def get_function_count(self) -> int:
        modules = getattr(self._result, "modules", [])
        return sum(len(getattr(m, "functions", [])) for m in modules)

    def get_class_count(self) -> int:
        modules = getattr(self._result, "modules", [])
        return sum(len(getattr(m, "classes", [])) for m in modules)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._result, name)


class ProjectAnalyzer:
    """Backward-compat wrapper: accepts (config) or (root_path, ...) as first arg."""

    def __init__(self, root_path_or_config: Any = ".", **kwargs: Any) -> None:
        if isinstance(root_path_or_config, (FilterConfig, Config)):
            self._config = root_path_or_config
            self._root_path: str | None = None
        else:
            self._config = None
            self._root_path = str(root_path_or_config)

    def analyze_project(self, path: str | None = None) -> _AnalysisResultWrapper:
        target = path or self._root_path or "."
        analyzer = _ProjectAnalyzer(root_path=target)
        result = analyzer.analyze()
        return _AnalysisResultWrapper(result, target)
