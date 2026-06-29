"""Exporters for analysis results."""

from __future__ import annotations

import json
import re
from typing import Any


def _as_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, dict):
        return result
    return {"result": str(result)}


class BaseExporter:
    """Base class for all exporters."""

    def export(self, result: Any, output_path: str, **kwargs: Any) -> None:
        raise NotImplementedError


class JSONExporter(BaseExporter):
    """Exports an analysis result to JSON."""

    def export(
        self, result: Any, output_path: str, compact: bool = False, **kwargs: Any
    ) -> None:
        data = _as_dict(result)
        with open(output_path, "w", encoding="utf-8") as handle:
            if compact:
                json.dump(data, handle, separators=(",", ":"), ensure_ascii=False)
            else:
                json.dump(data, handle, indent=2, ensure_ascii=False)


class MermaidExporter(BaseExporter):
    """Exports a call graph to a Mermaid ``flowchart`` diagram."""

    @staticmethod
    def _node_id(name: str) -> str:
        return "n_" + re.sub(r"\W+", "_", name)

    def export(self, result: Any, output_path: str, **kwargs: Any) -> None:
        functions = getattr(result, "functions", {}) or {}

        lines = ["flowchart TD"]
        for qname, info in functions.items():
            node_id = self._node_id(qname)
            label = getattr(info, "name", None) or qname
            lines.append(f'    {node_id}["{label}"]')

        for qname, info in functions.items():
            src = self._node_id(qname)
            for callee in getattr(info, "calls", []) or []:
                lines.append(f"    {src} --> {self._node_id(callee)}")

        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
