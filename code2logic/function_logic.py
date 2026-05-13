from __future__ import annotations

from typing import List, Tuple

from .models import FunctionInfo, ProjectInfo
from .shared_utils import remove_self_from_params, truncate_docstring
from .toon_format import TOONGenerator


class FunctionLogicGenerator:
    FILE_EXTENSION: str = ".functions.logicml"

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def generate(self, project: ProjectInfo, detail: str = "full") -> str:
        if detail == "detailed":
            detail = "full"
        lines: List[str] = []

        for module in project.modules:
            items: List[Tuple[str, str, FunctionInfo]] = []

            for f in module.functions:
                items.append(("function", f.name, f))

            for cls in module.classes:
                for method in cls.methods:
                    items.append(("method", f"{cls.name}.{method.name}", method))

            if not items:
                continue

            lines.append(
                f"# {module.path} | {module.language} | {len(items)} functions"
            )
            lines.append("functions:")

            for kind, qname, func in items:
                lines.extend(
                    self._format_function(
                        kind,
                        qname,
                        func,
                        detail,
                        indent=2,
                        module_language=module.language,
                    )
                )

            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def generate_json(self, project: ProjectInfo, detail: str = "full") -> str:
        if detail == "detailed":
            detail = "full"
        import json

        data = self._build_data(project, detail)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def generate_yaml(self, project: ProjectInfo, detail: str = "full") -> str:
        if detail == "detailed":
            detail = "full"
        data = self._build_data(project, detail)
        try:
            import yaml
        except ImportError:
            return self.generate(project, detail)
        return yaml.dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

    def generate_toon(
        self,
        project: ProjectInfo,
        detail: str = "full",
        no_repeat_name: bool = False,
        no_repeat_details: bool = False,
        include_does: bool = False,
        context: str = "none",
    ) -> str:
        """Generate function-logic in TOON format.

        Args:
            context: Structural context level:
                'none'    - flat function list (original behavior)
                'minimal' - class headers (name, bases) before methods
                'full'    - class headers + properties + module imports
        """
        if detail == "detailed":
            detail = "full"
        toon = TOONGenerator()
        delim = toon.delimiter
        dm = toon.delim_marker

        # Pre-filter: only modules with at least one function/method
        all_modules = list(project.modules or [])
        modules_with_items = [(m, self._module_items(m)) for m in all_modules]
        modules_with_items = [(m, items) for m, items in modules_with_items if items]

        lines: List[str] = []

        # Format header — helps LLM understand the structure
        ctx_label = f" | context:{context}" if context != "none" else ""
        lines.append(
            f"# {project.name} function-logic | {len(modules_with_items)} modules{ctx_label}"
        )
        lines.append(
            "# Convention: name with . = method, ~name = async, cc:N shown only when >1"
        )
        if context != "none":
            lines.append(
                "# CLASS: header before methods gives structural context (bases, props)"
            )

        lines.append(f"project: {toon._quote(project.name)}")
        if getattr(project, "generated_at", None):
            lines.append(f"generated: {toon._quote(project.generated_at)}")

        lines.append(f"modules[{len(modules_with_items)}]{{path{dm}lang{dm}items}}:")
        prev_dir: str | None = None
        for m, items in modules_with_items:
            if no_repeat_name:
                compressed_path, prev_dir = toon._compress_module_path(m.path, prev_dir)
                path_out = compressed_path
            else:
                path_out = m.path
            lines.append(
                f"  {toon._quote(path_out)}{delim}{toon._short_lang(m.language)}{delim}{len(items)}"
            )

        lines.append("")
        lines.append("function_details:")

        prev_dir = None
        for m, items in modules_with_items:
            if no_repeat_details:
                compressed_path, prev_dir = toon._compress_module_path(m.path, prev_dir)
                details_key = compressed_path
            else:
                details_key = m.path
            lines.append(f"  {toon._quote(details_key)}:")

            # Emit module imports for 'full' context
            if context == "full" and getattr(m, "imports", None):
                imports = [i for i in m.imports if i][:20]
                if imports:
                    lines.append(f"    imports[{len(imports)}]: {','.join(imports)}")

            # Emit class context headers before function table
            if context != "none":
                classes = getattr(m, "classes", []) or []
                if classes:
                    for cls in classes:
                        bases = ",".join(getattr(cls, "bases", []) or []) or "-"
                        cls_line = f"    CLASS {toon._quote(cls.name)}({bases})"
                        if context == "full":
                            props = getattr(cls, "properties", []) or []
                            if props:
                                cls_line += f" props:[{','.join(props[:15])}]"
                        lines.append(cls_line)

            header = f"line{dm}name{dm}sig"
            if include_does and detail in ("standard", "full"):
                header += f"{dm}does"
            if detail == "full":
                header += f"{dm}decorators{dm}calls{dm}raises"

            lines.append(f"    functions[{len(items)}]{{{header}}}:")

            for kind, qname, func in items:
                sig = self._build_sig(
                    func, include_async_prefix=False, language=m.language
                )
                start_line = str(getattr(func, "start_line", 0) or 0)

                # Encode async as ~ prefix, cc as suffix (only when >1)
                display_name = qname
                if getattr(func, "is_async", False):
                    display_name = f"~{qname}"
                cc = getattr(func, "complexity", 1) or 1
                if cc > 1:
                    display_name = f"{display_name} cc:{cc}"

                row = [
                    start_line,
                    toon._quote(display_name),
                    toon._quote(sig),
                ]

                if include_does and detail in ("standard", "full"):
                    does = self._build_does(func)
                    row.append(toon._quote(does))

                if detail == "full":
                    decorators = (
                        "|".join((getattr(func, "decorators", []) or [])[:10]) or "-"
                    )
                    calls = "|".join((getattr(func, "calls", []) or [])[:40]) or "-"
                    raises = "|".join((getattr(func, "raises", []) or [])[:20]) or "-"
                    row.append(toon._quote(decorators))
                    row.append(toon._quote(calls))
                    row.append(toon._quote(raises))

                lines.append(f"      {delim.join(row)}")

        return "\n".join(lines).rstrip() + "\n"

    def generate_toon_schema(self) -> str:
        """Generate JSON Schema describing the function-logic TOON format."""
        import json

        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Function Logic TOON",
            "type": "object",
            "description": (
                "Schema for function-logic TOON output (e.g. function.toon) — compact function/method index. "
                "Generated by code2logic with --function-logic and TOON format."
            ),
            "properties": {
                "project": {"type": "string", "description": "Project name"},
                "generated": {"type": "string", "description": "ISO timestamp"},
                "modules": {
                    "type": "array",
                    "description": "Modules with at least one function/method. Rows: path,lang,items. Use ./file for same-dir compression (--no-repeat-module).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative path or ./basename if same dir as previous",
                            },
                            "lang": {
                                "type": "string",
                                "description": "Short language code (py, js, ts, ...)",
                            },
                            "items": {
                                "type": "integer",
                                "description": "Number of functions+methods in module",
                            },
                        },
                    },
                },
                "function_details": {
                    "type": "object",
                    "description": "Per-module function tables. Keys are module paths (or ./basename with --no-repeat-details).",
                    "patternProperties": {
                        ".*": {
                            "type": "object",
                            "properties": {
                                "functions": {
                                    "type": "array",
                                    "description": "Tabular rows: line,name,sig[,does][,decorators,calls,raises]",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "line": {
                                                "type": "integer",
                                                "description": "Start line number",
                                            },
                                            "name": {
                                                "type": "string",
                                                "description": (
                                                    "Function or method name. "
                                                    "Contains '.' if method (e.g. Class.method). "
                                                    "Prefixed with ~ if async. "
                                                    "Suffixed with ' cc:N' if cyclomatic complexity > 1."
                                                ),
                                            },
                                            "sig": {
                                                "type": "string",
                                                "description": "Signature: (params) [-> return_type]",
                                            },
                                            "does": {
                                                "type": "string",
                                                "description": "Intent/purpose (standard+full detail)",
                                            },
                                            "decorators": {
                                                "type": "string",
                                                "description": "Pipe-separated decorators (full detail)",
                                            },
                                            "calls": {
                                                "type": "string",
                                                "description": "Pipe-separated function calls (full detail)",
                                            },
                                            "raises": {
                                                "type": "string",
                                                "description": "Pipe-separated exceptions (full detail)",
                                            },
                                        },
                                    },
                                }
                            },
                        }
                    },
                },
            },
        }
        return json.dumps(schema, indent=2, ensure_ascii=False)

    def _build_data(self, project: ProjectInfo, detail: str) -> dict:
        modules_data = []
        for m in project.modules or []:
            items = self._module_items(m)
            if not items:
                continue
            modules_data.append(
                {
                    "path": m.path,
                    "language": m.language,
                    "functions": [
                        self._item_to_dict(
                            kind, qname, func, detail, module_language=m.language
                        )
                        for kind, qname, func in items
                    ],
                }
            )

        data = {
            "project": project.name,
            "generated_at": getattr(project, "generated_at", ""),
            "modules": modules_data,
        }
        return data

    def _module_items(self, module) -> List[Tuple[str, str, FunctionInfo]]:
        items: List[Tuple[str, str, FunctionInfo]] = []

        for f in getattr(module, "functions", []) or []:
            items.append(("function", f.name, f))

        for cls in getattr(module, "classes", []) or []:
            for method in getattr(cls, "methods", []) or []:
                items.append(("method", f"{cls.name}.{method.name}", method))

        return items

    def _build_sig(
        self, func: FunctionInfo, include_async_prefix: bool = True, language: str = ""
    ) -> str:
        clean_params = remove_self_from_params((func.params or [])[:10])
        params_str = ", ".join(clean_params)
        ret = getattr(func, "return_type", None)
        if isinstance(ret, str):
            ret = ret.strip()

        if language in ("javascript", "typescript") and ret == "None":
            ret = None

        sig = f"({params_str})" if params_str else "()"
        if ret:
            sig = f"{sig} -> {ret}"
        if include_async_prefix and getattr(func, "is_async", False):
            sig = f"async {sig}"
        return sig

    def _build_loc(self, func: FunctionInfo) -> str:
        start_line = getattr(func, "start_line", 0) or 0
        end_line = getattr(func, "end_line", 0) or 0
        if start_line and end_line:
            return f"{start_line}-{end_line}"
        return "-"

    def _build_does(self, func: FunctionInfo) -> str:
        does_src = func.docstring or func.intent or ""
        does = truncate_docstring(does_src, max_length=120) if does_src else ""
        does = does.replace("\n", " ").replace('"', "'").strip()
        return does or "-"

    def _item_to_dict(
        self,
        kind: str,
        qualified_name: str,
        func: FunctionInfo,
        detail: str,
        module_language: str = "",
    ) -> dict:
        data = {
            "name": qualified_name,
            "kind": kind,
            "sig": self._build_sig(
                func, include_async_prefix=True, language=module_language
            ),
        }

        start_line = getattr(func, "start_line", 0) or 0
        end_line = getattr(func, "end_line", 0) or 0
        if start_line:
            data["start_line"] = start_line
        if end_line:
            data["end_line"] = end_line

        if detail in ("standard", "full"):
            does = self._build_does(func)
            if does and does != "-":
                data["does"] = does

        if detail == "full":
            if getattr(func, "lines", 0):
                data["lines"] = func.lines
            if getattr(func, "complexity", 0):
                data["complexity"] = func.complexity

            decorators = getattr(func, "decorators", []) or []
            if decorators:
                data["decorators"] = decorators[:10]

            calls = getattr(func, "calls", []) or []
            if calls:
                data["calls"] = calls[:40]

            raises = getattr(func, "raises", []) or []
            if raises:
                data["raises"] = raises[:20]

        return data

    def _format_function(
        self,
        kind: str,
        qualified_name: str,
        func: FunctionInfo,
        detail: str,
        indent: int,
        module_language: str = "",
    ) -> List[str]:
        prefix = " " * indent
        sub = " " * (indent + 2)

        lines: List[str] = [f"{prefix}{qualified_name}:"]

        lines.append(f"{sub}kind: {kind}")

        sig = self._build_sig(func, include_async_prefix=True, language=module_language)
        lines.append(f"{sub}sig: {sig}")

        loc = self._build_loc(func)
        if loc != "-":
            lines.append(f"{sub}loc: {loc}")

        if detail in ("standard", "full"):
            does = self._build_does(func)
            if does != "-":
                lines.append(f'{sub}does: "{does}"')

        if detail == "full":
            if getattr(func, "lines", 0):
                lines.append(f"{sub}lines: {func.lines}")
            if getattr(func, "complexity", 0):
                lines.append(f"{sub}complexity: {func.complexity}")

            decorators = getattr(func, "decorators", []) or []
            if decorators:
                lines.append(f"{sub}decorators: [{', '.join(decorators[:10])}]")

            if getattr(func, "calls", None):
                calls = func.calls or []
                if calls:
                    lines.append(f"{sub}calls: [{', '.join(calls[:40])}]")

            if getattr(func, "raises", None):
                raises = func.raises or []
                if raises:
                    lines.append(f"{sub}raises: [{', '.join(raises[:20])}]")

        return lines
