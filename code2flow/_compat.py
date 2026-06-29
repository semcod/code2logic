# Backward-compat wrappers for the old code2flow analysis API.
#
# code2logic ships an LLM-oriented analyzer whose result model does not match
# the classic AST-based code2flow contract (a flat ``functions`` / ``classes``
# mapping, nested-class discovery, recursion / state-machine pattern detection
# and cache statistics).  This module provides a small, self-contained AST
# walker that reproduces that contract.
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from code2flow.core.analyzer import FastFileFilter, FileCache
from code2flow.core.config import (
    AnalysisConfig,
    FilterConfig,
    PerformanceConfig,
)
from code2flow.core.models import AnalysisResult, ClassInfo, FunctionInfo, Pattern

# Backward-compat alias used by callers that import ``Config`` from here.
Config = AnalysisConfig

# Attribute names that strongly suggest a class models a state machine.
_STATE_ATTRS = {"state", "_state", "status", "_status", "phase", "_phase"}


def _resolve_config(arg: Any) -> AnalysisConfig:
    if isinstance(arg, AnalysisConfig):
        return arg
    if isinstance(arg, FilterConfig):
        return AnalysisConfig(filters=arg)
    return AnalysisConfig()


def _called_names(node: ast.AST) -> list[str]:
    """Collect the simple names of every call made within ``node``."""
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
    return names


def _has_property_decorator(node: ast.AST) -> bool:
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name) and dec.id == "property":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "property":
            return True
    return False


def _self_state_assignments(class_node: ast.ClassDef) -> dict[str, set[str]]:
    """Map ``self.<attr>`` -> set of method names that assign it."""
    assigned: dict[str, set[str]] = {}
    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(item):
            if not isinstance(sub, ast.Assign):
                continue
            for target in sub.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    assigned.setdefault(target.attr, set()).add(item.name)
    return assigned


class _FileAnalysis:
    """Plain container for one file's extracted entities (cacheable)."""

    def __init__(self) -> None:
        self.functions: list[dict] = []
        self.classes: list[dict] = []
        self.patterns: list[dict] = []


def _analyze_source(source: str, file_path: str) -> _FileAnalysis:
    analysis = _FileAnalysis()
    tree = ast.parse(source)

    def walk(node: ast.AST, prefix: str, class_stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{prefix}.{child.name}" if prefix else child.name
                calls = _called_names(child)
                start = child.lineno
                end = getattr(child, "end_lineno", start) or start
                analysis.functions.append(
                    {
                        "name": child.name,
                        "qualified_name": qname,
                        "file": file_path,
                        "line": start,
                        "lines": end - start + 1,
                        "calls": sorted(set(calls)),
                        "is_private": child.name.startswith("_"),
                        "is_property": _has_property_decorator(child),
                        "is_method": bool(class_stack),
                    }
                )
                # Recursion: function calls itself by name.
                if child.name in calls:
                    analysis.patterns.append(
                        {"type": "recursion", "name": qname, "detail": "self-call"}
                    )
                # Recurse into the function body for nested defs / classes.
                walk(child, qname, class_stack)

            elif isinstance(child, ast.ClassDef):
                qname = f"{prefix}.{child.name}" if prefix else child.name
                analysis.classes.append(
                    {
                        "name": child.name,
                        "qualified_name": qname,
                        "file": file_path,
                        "line": child.lineno,
                    }
                )
                # State-machine detection: a recognised state attribute is
                # assigned in two or more methods (i.e. transitions occur).
                assignments = _self_state_assignments(child)
                for attr, methods in assignments.items():
                    if attr.lower() in _STATE_ATTRS and len(methods) >= 2:
                        analysis.patterns.append(
                            {
                                "type": "state_machine",
                                "name": qname,
                                "detail": f"transitions on '{attr}'",
                            }
                        )
                        break
                walk(child, qname, class_stack + [child.name])

    walk(tree, "", [])
    return analysis


class _AnalysisResultWrapper(AnalysisResult):
    """AnalysisResult subclass returned by the compat analyzer."""


class ProjectAnalyzer:
    """Backward-compat AST-based project analyzer."""

    def __init__(self, root_path_or_config: Any = ".", **kwargs: Any) -> None:
        if isinstance(root_path_or_config, (FilterConfig, AnalysisConfig)):
            self._config = _resolve_config(root_path_or_config)
            self._root_path: str | None = None
        else:
            self._config = AnalysisConfig()
            self._root_path = str(root_path_or_config)

    @property
    def config(self) -> AnalysisConfig:
        return self._config

    def _cache(self) -> FileCache | None:
        perf: PerformanceConfig = self._config.performance
        if perf.enable_cache and perf.cache_dir:
            return FileCache(cache_dir=perf.cache_dir)
        return None

    def analyze_project(self, path: str | None = None) -> _AnalysisResultWrapper:
        target = path or self._root_path or "."
        if not os.path.isdir(target):
            raise FileNotFoundError(
                f"Path does not exist or is not a directory: {target}"
            )

        file_filter = FastFileFilter(self._config.filters)
        filters = self._config.filters
        cache = self._cache()

        result = _AnalysisResultWrapper(
            project_path=str(target), analysis_mode="static"
        )
        files_processed = 0
        cache_hits = 0

        for py_file in sorted(Path(target).rglob("*.py")):
            file_path = str(py_file)
            if not file_filter.should_process(file_path):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            file_analysis: _FileAnalysis | None = None
            if cache is not None:
                cached = cache.get(file_path, source)
                if cached is not None:
                    file_analysis = cached
                    cache_hits += 1

            if file_analysis is None:
                try:
                    file_analysis = _analyze_source(source, file_path)
                except SyntaxError:
                    continue
                if cache is not None:
                    cache.put(file_path, source, file_analysis)

            files_processed += 1

            for fn in file_analysis.functions:
                if filters.skip_private and fn["is_private"]:
                    continue
                if filters.skip_properties and fn["is_property"]:
                    continue
                if fn["lines"] < filters.min_function_lines:
                    continue
                key = f"{fn['file']}::{fn['qualified_name']}"
                result.functions[key] = FunctionInfo(
                    name=fn["name"],
                    qualified_name=fn["qualified_name"],
                    file=fn["file"],
                    line=fn["line"],
                    calls=list(fn["calls"]),
                )

            for cls in file_analysis.classes:
                cls_key = f"{cls['file']}::{cls['qualified_name']}"
                result.classes[cls_key] = ClassInfo(
                    name=cls["name"],
                    qualified_name=cls["qualified_name"],
                    file=cls["file"],
                    line=cls["line"],
                )

            for pat in file_analysis.patterns:
                result.patterns.append(
                    Pattern(type=pat["type"], name=pat["name"], detail=pat["detail"])
                )

        # Populate ``called_by`` edges between resolved functions.
        for fn in result.functions.values():
            for callee in fn.calls:
                for other in result.functions.values():
                    if (
                        other.name == callee
                        and other.qualified_name != fn.qualified_name
                    ):
                        other.called_by.append(fn.qualified_name)

        result.stats = {"files_processed": files_processed, "cache_hits": cache_hits}
        return result
