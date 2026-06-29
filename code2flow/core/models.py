"""Lightweight analysis result models used by exporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FunctionInfo:
    name: str = ""
    qualified_name: str = ""
    file: str = ""
    line: int = 0
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file": self.file,
            "line": self.line,
            "calls": list(self.calls),
            "called_by": list(self.called_by),
        }


@dataclass
class ClassInfo:
    name: str = ""
    qualified_name: str = ""
    file: str = ""
    line: int = 0
    methods: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file": self.file,
            "line": self.line,
            "methods": list(self.methods),
            "bases": list(self.bases),
        }


@dataclass
class Pattern:
    type: str = ""
    name: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "name": self.name, "detail": self.detail}


@dataclass
class AnalysisResult:
    project_path: str = ""
    analysis_mode: str = "static"
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    patterns: list[Pattern] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def get_function_count(self) -> int:
        return len(self.functions)

    def get_class_count(self) -> int:
        return len(self.classes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "analysis_mode": self.analysis_mode,
            "functions": {k: v.to_dict() for k, v in self.functions.items()},
            "classes": {k: v.to_dict() for k, v in self.classes.items()},
            "patterns": [p.to_dict() for p in self.patterns],
            "stats": dict(self.stats),
        }
