"""
TOON Format Generator for Code2Logic.

TOON (Token-Oriented Object Notation) is a compact, human-readable encoding
of JSON that minimizes tokens for LLM input. It combines YAML-like indentation
with CSV-style tabular arrays.

See: https://github.com/toon-format/toon
"""

import re
from typing import Any, Dict, List

from .models import ClassInfo, FunctionInfo, ModuleInfo, ProjectInfo, TypeInfo
from .shared_utils import compact_imports, truncate_docstring

CONSTANT_3 = 3
CONSTANT_4 = 4
CONSTANT_5 = 5
CONSTANT_6 = 6
CONSTANT_7 = 7
CONSTANT_8 = 8
PORT_15 = 15
CONSTANT_20 = 20
CONSTANT_25 = 25
CONSTANT_40 = 40
CONSTANT_80 = 80
CONSTANT_117 = 117
CONSTANT_120 = 120
CONSTANT_1024 = 1024


CONSTANT_3 = CONSTANT_3
CONSTANT_4 = CONSTANT_4
CONSTANT_5 = CONSTANT_5
CONSTANT_6 = CONSTANT_6
CONSTANT_7 = CONSTANT_7
CONSTANT_8 = CONSTANT_8
PORT_15 = PORT_15
CONSTANT_20 = CONSTANT_20
CONSTANT_25 = CONSTANT_25
CONSTANT_40 = CONSTANT_40
CONSTANT_80 = CONSTANT_80
CONSTANT_117 = CONSTANT_117
CONSTANT_120 = CONSTANT_120
CONSTANT_1024 = CONSTANT_1024


CONSTANT_3 = CONSTANT_3
CONSTANT_4 = CONSTANT_4
CONSTANT_5 = CONSTANT_5
CONSTANT_6 = CONSTANT_6
CONSTANT_7 = CONSTANT_7
CONSTANT_8 = CONSTANT_8
PORT_15 = PORT_15
CONSTANT_20 = CONSTANT_20
CONSTANT_25 = CONSTANT_25
CONSTANT_40 = CONSTANT_40
CONSTANT_80 = CONSTANT_80
CONSTANT_117 = CONSTANT_117
CONSTANT_120 = CONSTANT_120
CONSTANT_1024 = CONSTANT_1024


CONSTANT_3 = CONSTANT_3
CONSTANT_4 = CONSTANT_4
CONSTANT_5 = CONSTANT_5
CONSTANT_6 = CONSTANT_6
CONSTANT_7 = CONSTANT_7
CONSTANT_8 = CONSTANT_8
PORT_15 = PORT_15
CONSTANT_20 = CONSTANT_20
CONSTANT_25 = CONSTANT_25
CONSTANT_40 = CONSTANT_40
CONSTANT_80 = CONSTANT_80
CONSTANT_117 = CONSTANT_117
CONSTANT_120 = CONSTANT_120
CONSTANT_1024 = CONSTANT_1024


class TOONGenerator:
    """
    Generates TOON format output from ProjectInfo.

    TOON is optimized for LLM consumption with:
    - Minimal tokens (40% fewer than JSON)
    - Tabular arrays for uniform data
    - YAML-like indentation for structure

    Usage:
        gen = TOONGenerator()
        toon_output = gen.generate(project_info)
    """

    # Characters that require quoting in TOON
    SPECIAL_CHARS = re.compile(r"[:\"\\\[\]\{\}\n\t\r,]")
    LOOKS_LIKE_LITERAL = re.compile(r"^(true|false|null|-?\d+\.?\d*([eE][+-]?\d+)?|-)$")

    LANGUAGE_ABBREVIATIONS = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "tsx": "tsx",
        "jsx": "jsx",
        "java": "java",
        "kotlin": "kt",
        "go": "go",
        "rust": "rs",
        "c": "c",
        "cpp": "cpp",
        "c++": "cpp",
        "csharp": "cs",
        "c#": "cs",
        "php": "php",
        "ruby": "rb",
        "swift": "swift",
        "scala": "scala",
        "bash": "sh",
        "shell": "sh",
        "sql": "sql",
        "yaml": "yaml",
        "json": "json",
        "toml": "toml",
        "markdown": "md",
        "html": "html",
        "css": "css",
        "dockerfile": "docker",
    }

    def __init__(self, delimiter: str = ",", use_tabs: bool = False):
        """
        Initialize TOON generator.

        Args:
            delimiter: Field delimiter for arrays (',' or '\t' or '|')
            use_tabs: Use tab delimiter for better token efficiency
        """
        self.delimiter = "\t" if use_tabs else delimiter
        # Field names inside `{...}` must be explicitly separated so both humans and
        # parsers/LLMs can read them. Use comma-separated headers regardless of row delimiter.
        self.delim_marker = ","

    def _short_lang(self, lang: str) -> str:
        lang_norm = (lang or "").strip().lower()
        return self.LANGUAGE_ABBREVIATIONS.get(lang_norm, lang)

    def _compress_module_path(self, path: str, prev_dir: str | None) -> tuple[str, str]:
        """Compress repeated directory prefixes for module summary tables.

        If consecutive modules are in the same directory, emit './<basename>' instead
        of repeating '<dir>/<basename>'. The first entry for a directory stays as the
        full path.
        """
        p = path or ""
        if "/" not in p:
            return p, ""

        cur_dir, base = p.rsplit("/", 1)
        if prev_dir is not None and cur_dir == prev_dir:
            return f"./{base}", cur_dir
        return p, cur_dir

    def generate(
        self,
        project: ProjectInfo,
        detail: str = "standard",
        no_repeat_name: bool = False,
    ) -> str:
        """
        Generate TOON format from ProjectInfo.

        Args:
            project: Analyzed project info
            detail: Level of detail ('compact', 'standard', 'full')

        Returns:
            TOON formatted string
        """
        lines = []

        # Project metadata
        lines.append(f"project: {self._quote(project.name)}")
        lines.append(f"root: {self._quote(project.root_path)}")
        lines.append(f"generated: {project.generated_at}")

        # Statistics as nested object
        lines.append("stats:")
        lines.append(f"  files: {project.total_files}")
        lines.append(f"  lines: {project.total_lines}")

        # Languages as primitive array
        if project.languages:
            lang_items = [
                f"{self._short_lang(k)}:{v}" for k, v in project.languages.items()
            ]
            lines.append(
                f"  languages[{len(lang_items)}]: {self.delimiter.join(lang_items)}"
            )

        # Modules - tabular format for efficiency
        if project.modules:
            lines.append("")
            lines.extend(
                self._generate_modules(
                    project.modules, detail, no_repeat_name=no_repeat_name
                )
            )

        return "\n".join(lines)

    def generate_hybrid(
        self,
        project: ProjectInfo,
        detail: str = "full",
        no_repeat_name: bool = True,
        hub_top_n: int = CONSTANT_5,
        hub_functions_detail: str = "full",
    ) -> str:
        """Generate TOON-Hybrid: project structure + function-logic for hub modules.

        Combines project-level TOON (classes, imports, structure) with
        selective function-logic details for the most important modules.

        Args:
            project: Analyzed project info
            detail: Detail level for project structure
            no_repeat_name: Compress repeated directory prefixes
            hub_top_n: Number of top modules to include function details for
            hub_functions_detail: Detail level for function-logic ('standard', 'full')

        Returns:
            Hybrid TOON string
        """
        from .function_logic import FunctionLogicGenerator

        # Generate base project TOON
        base = self.generate(project, detail=detail, no_repeat_name=no_repeat_name)

        # Identify hub modules: use dependency_metrics if available, otherwise sort by function count
        hub_paths: set = set()
        dep_metrics = getattr(project, "dependency_metrics", {}) or {}
        if dep_metrics:
            ranked = sorted(
                dep_metrics.items(),
                key=lambda x: getattr(x[1], "pagerank", 0),
                reverse=True,
            )
            hub_paths = {path for path, node in ranked[:hub_top_n]}
        else:
            # Fallback: rank by total functions + methods
            def _item_count(m):
                return len(getattr(m, "functions", []) or []) + sum(
                    len(getattr(c, "methods", []) or [])
                    for c in (getattr(m, "classes", []) or [])
                )

            ranked_modules = sorted(project.modules, key=_item_count, reverse=True)
            hub_paths = {m.path for m in ranked_modules[:hub_top_n]}

        if not hub_paths:
            return base

        # Generate function-logic section for hub modules only
        hub_modules = [m for m in project.modules if m.path in hub_paths]
        if not hub_modules:
            return base

        logic_gen = FunctionLogicGenerator()
        lines = [base, "", "# === Hub Module Function Details ==="]

        for m in hub_modules:
            items = logic_gen._module_items(m)
            if not items:
                continue
            lines.append(f"  {self._quote(m.path)}:")

            # Emit class context
            classes = getattr(m, "classes", []) or []
            for cls in classes:
                bases = ",".join(getattr(cls, "bases", []) or []) or "-"
                lines.append(f"    CLASS {self._quote(cls.name)}({bases})")

            # Emit function table
            header = f"line{self.delim_marker}name{self.delim_marker}sig{self.delim_marker}does"
            lines.append(f"    functions[{len(items)}]{{{header}}}:")

            for kind, qname, func in items:
                sig = logic_gen._build_sig(
                    func, include_async_prefix=False, language=m.language
                )
                start_line = str(getattr(func, "start_line", 0) or 0)
                display_name = qname
                if getattr(func, "is_async", False):
                    display_name = f"~{qname}"
                cc = getattr(func, "complexity", 1) or 1
                if cc > 1:
                    display_name = f"{display_name} cc:{cc}"
                does = logic_gen._build_does(func)
                row = [
                    start_line,
                    self._quote(display_name),
                    self._quote(sig),
                    self._quote(does),
                ]
                lines.append(f"      {self.delimiter.join(row)}")

        return "\n".join(lines)

    def _generate_modules(
        self, modules: List[ModuleInfo], detail: str, no_repeat_name: bool = False
    ) -> List[str]:
        """Generate modules section."""
        lines = []

        # Module summary as tabular array
        lines.append(
            f"modules[{len(modules)}]{{path{self.delim_marker}lang{self.delim_marker}lines{self.delim_marker}kb}}:"
        )
        prev_dir: str | None = None
        for m in modules:
            if no_repeat_name:
                path_out, prev_dir = self._compress_module_path(m.path, prev_dir)
            else:
                path_out = m.path
            path = self._quote(path_out)
            kb = round((getattr(m, "file_bytes", 0) or 0) / CONSTANT_1024, 1)
            lines.append(
                f"  {path}{self.delimiter}{self._short_lang(m.language)}{self.delimiter}{m.lines_code}{self.delimiter}{kb}"
            )

        # Detailed module info
        if detail in ("standard", "full"):
            lines.append("")
            lines.append("module_details:")

            for m in modules:
                lines.append(f"  {self._quote(m.path)}:")

                # ENHANCED: Add imports for better reproduction
                if m.imports:
                    imports_str = self.delimiter.join(
                        self._quote(x) for x in m.imports[:PORT_15]
                    )
                    lines.append(f"    imports[{len(m.imports)}]: {imports_str}")

                # ENHANCED: Add exports
                if m.exports:
                    exports_str = self.delimiter.join(
                        self._quote(x) for x in m.exports[:10]
                    )
                    lines.append(f"    exports[{len(m.exports)}]: {exports_str}")

                # ENHANCED: Add constants with values/keys (critical for reproduction)
                constants_attr = getattr(m, "constants", []) or []
                const_rows = []
                for c in constants_attr:
                    if isinstance(c, str):
                        if c.startswith("conditional:"):
                            continue
                        const_rows.append({"n": c, "t": "-", "v": "-", "keys": "-"})
                    else:
                        keys = getattr(c, "value_keys", None) or []
                        v = getattr(c, "value", None)
                        t = getattr(c, "type_annotation", "") or "-"
                        if keys:
                            const_rows.append(
                                {
                                    "n": c.name,
                                    "t": t,
                                    "v": "-",
                                    "keys": "|".join(keys[:10]),
                                }
                            )
                        elif v:
                            v_snip = v.replace("\n", " ").strip()
                            if len(v_snip) > CONSTANT_120:
                                v_snip = v_snip[:CONSTANT_117] + "..."
                            const_rows.append(
                                {"n": c.name, "t": t, "v": v_snip, "keys": "-"}
                            )
                        else:
                            const_rows.append(
                                {"n": c.name, "t": t, "v": "-", "keys": "-"}
                            )
                    if len(const_rows) >= CONSTANT_8:
                        break

                if const_rows:
                    header = f"n{self.delim_marker}t{self.delim_marker}v{self.delim_marker}keys"
                    lines.append(f"    const[{len(const_rows)}]{{{header}}}:")
                    for r in const_rows:
                        lines.append(
                            f"      {self._quote(r['n'])}{self.delimiter}{self._quote(r['t'])}{self.delimiter}{self._quote(r['v'])}{self.delimiter}{self._quote(r['keys'])}"
                        )

                # Types (enums/interfaces/type aliases) - critical for reproduction of enum values
                if getattr(m, "types", None):
                    lines.extend(self._generate_types(m.types, indent=CONSTANT_4))

                # Classes
                if m.classes:
                    lines.extend(
                        self._generate_classes(m.classes, detail, indent=CONSTANT_4)
                    )

                # Functions
                if m.functions:
                    lines.extend(
                        self._generate_functions(m.functions, detail, indent=CONSTANT_4)
                    )

        return lines

    def _generate_types(self, types: List[TypeInfo], indent: int = 0) -> List[str]:
        """Generate module-level types in TOON format (with enum values where available)."""
        lines: List[str] = []
        ind = " " * indent

        rows = []
        for t in types[:CONSTANT_25]:
            kind = getattr(t, "kind", "") or "-"
            name = getattr(t, "name", "") or "-"
            definition = getattr(t, "definition", "") or "-"
            values = getattr(t, "values", None)

            def_snip = definition.replace("\n", " ").strip() if definition else "-"
            if def_snip and len(def_snip) > CONSTANT_120:
                def_snip = def_snip[:CONSTANT_117] + "..."

            values_str = "-"
            if values:
                values_str = "|".join(
                    str(v).replace("\n", " ").strip() for v in values[:CONSTANT_20]
                )

            rows.append(
                {
                    "name": name,
                    "kind": kind,
                    "values": values_str,
                    "def": def_snip or "-",
                }
            )

        if not rows:
            return lines

        header = f"name{self.delim_marker}kind{self.delim_marker}values{self.delim_marker}def"
        lines.append(f"{ind}types[{len(rows)}]{{{header}}}:")
        for r in rows:
            lines.append(
                f"{ind}  {self._quote(r['name'])}{self.delimiter}{self._quote(r['kind'])}{self.delimiter}{self._quote(r['values'])}{self.delimiter}{self._quote(r['def'])}"
            )
        return lines

    def _generate_classes(
        self, classes: List[ClassInfo], detail: str, indent: int = 0
    ) -> List[str]:
        """Generate classes in TOON format."""
        lines = []
        ind = " " * indent

        # ENHANCED: Richer tabular format with decorators
        header_fields = f"name{self.delim_marker}bases{self.delim_marker}decorators{self.delim_marker}props{self.delim_marker}methods"
        lines.append(f"{ind}classes[{len(classes)}]{{{header_fields}}}:")

        for c in classes:
            name = self._quote(c.name)
            bases = "|".join(c.bases) if c.bases else "-"
            # ClassInfo may not have decorators attribute
            class_decorators = getattr(c, "decorators", []) or []
            decorators = (
                "|".join(class_decorators[:CONSTANT_3]) if class_decorators else "-"
            )
            props = len(c.properties) if c.properties else 0
            method_count = len(c.methods)
            lines.append(
                f"{ind}  {name}{self.delimiter}{bases}{self.delimiter}{decorators}{self.delimiter}{props}{self.delimiter}{method_count}"
            )

        # Detailed class info with methods (for standard and full)
        if detail in ("standard", "full"):
            lines.append(f"{ind}class_details:")
            for c in classes:
                lines.append(f"{ind}  {self._quote(c.name)}:")

                # ENHANCED: Add docstring
                if c.docstring:
                    doc = c.docstring[:100].replace("\n", " ").strip()
                    lines.append(f"{ind}    doc: {self._quote(doc)}")

                # ENHANCED: Add properties with types
                if c.properties:
                    props_str = self.delimiter.join(
                        self._quote(x) for x in c.properties[:10]
                    )
                    lines.append(
                        f"{ind}    properties[{len(c.properties)}]: {props_str}"
                    )

                # ENHANCED: Dataclass fields
                if getattr(c, "is_dataclass", False) and getattr(c, "fields", None):
                    fields = c.fields[:CONSTANT_20]
                    header = f"n{self.delim_marker}t{self.delim_marker}default{self.delim_marker}factory"
                    lines.append(f"{ind}    fields[{len(fields)}]{{{header}}}:")
                    for f in fields:
                        t = getattr(f, "type_annotation", "") or "-"
                        dflt = getattr(f, "default", None) or "-"
                        fac = getattr(f, "default_factory", None) or "-"
                        lines.append(
                            f"{ind}      {self._quote(f.name)}{self.delimiter}{self._quote(t)}{self.delimiter}{self._quote(dflt)}{self.delimiter}{self._quote(fac)}"
                        )

                # Methods with full details
                if c.methods:
                    lines.extend(
                        self._generate_methods(c.methods, detail, indent + CONSTANT_4)
                    )

        return lines

    def _generate_methods(
        self, methods: List[FunctionInfo], detail: str = "standard", indent: int = 0
    ) -> List[str]:
        """Generate methods in tabular TOON format."""
        lines = []
        ind = " " * indent

        # ENHANCED: Richer tabular array for methods
        header = f"name{self.delim_marker}sig{self.delim_marker}decorators{self.delim_marker}async{self.delim_marker}lines"
        lines.append(f"{ind}methods[{len(methods)}]{{{header}}}:")

        for m in methods:
            name = self._quote(m.name)
            sig = self._quote(self._build_signature(m))
            method_decorators = getattr(m, "decorators", []) or []
            decorators = "|".join(method_decorators[:2]) if method_decorators else "-"
            is_async = "true" if getattr(m, "is_async", False) else "false"
            lines.append(
                f"{ind}  {name}{self.delimiter}{sig}{self.delimiter}{decorators}{self.delimiter}{is_async}{self.delimiter}{m.lines}"
            )

        # ENHANCED: Add intent/docstring for full detail
        if detail == "full":
            lines.append(f"{ind}method_docs:")
            for m in methods:
                if m.intent or m.docstring:
                    doc = (
                        (m.intent or m.docstring or "")[:CONSTANT_80]
                        .replace("\n", " ")
                        .strip()
                    )
                    if doc:
                        lines.append(
                            f"{ind}  {self._quote(m.name)}: {self._quote(doc)}"
                        )

        return lines

    def _generate_functions(
        self, functions: List[FunctionInfo], detail: str, indent: int = 0
    ) -> List[str]:
        """Generate functions in tabular TOON format."""
        lines = []
        ind = " " * indent

        # ENHANCED: Richer tabular array with decorators and category
        header = f"name{self.delim_marker}sig{self.delim_marker}decorators{self.delim_marker}async{self.delim_marker}category{self.delim_marker}lines"
        lines.append(f"{ind}functions[{len(functions)}]{{{header}}}:")

        for f in functions:
            name = self._quote(f.name)
            sig = self._quote(self._build_signature(f))
            func_decorators = getattr(f, "decorators", []) or []
            decorators = "|".join(func_decorators[:2]) if func_decorators else "-"
            is_async = "true" if getattr(f, "is_async", False) else "false"
            # category may not exist on FunctionInfo
            category = getattr(f, "category", None) or "-"
            lines.append(
                f"{ind}  {name}{self.delimiter}{sig}{self.delimiter}{decorators}{self.delimiter}{is_async}{self.delimiter}{category}{self.delimiter}{f.lines}"
            )

        # ENHANCED: Add intent/docstring for standard and full detail
        if detail in ("standard", "full"):
            has_docs = any(f.intent or f.docstring for f in functions)
            if has_docs:
                lines.append(f"{ind}function_docs:")
                for f in functions:
                    doc = (
                        (f.intent or f.docstring or "")[:100].replace("\n", " ").strip()
                    )
                    if doc:
                        lines.append(
                            f"{ind}  {self._quote(f.name)}: {self._quote(doc)}"
                        )

        return lines

    def _build_signature(self, f: FunctionInfo) -> str:
        """Build compact signature string without self/cls."""
        params = []
        for p in f.params[:CONSTANT_7]:  # +1 to account for self
            p_clean = p.replace("\n", " ").replace(",", ";").strip()
            # Skip self/cls - obvious for methods
            if p_clean in ("self", "cls"):
                continue
            if p_clean.startswith("self:"):
                continue
            if p_clean:
                params.append(p_clean)

        # Limit to 6 actual params
        if len(params) > CONSTANT_6:
            overflow = len(params) - CONSTANT_6
            params = params[:CONSTANT_6]
            params.append(f"...+{overflow}")

        param_str = ";".join(params)

        ret = getattr(f, "return_type", None)
        if isinstance(ret, str):
            ret = ret.strip()

        if ret:
            return f"({param_str})->{ret}"
        return f"({param_str})"

    def _quote(self, value: Any) -> str:
        """Quote a value if necessary for TOON format."""
        if value is None:
            return "null"

        s = str(value)

        # Empty string must be quoted
        if not s:
            return '""'

        # Check if quoting needed
        needs_quote = (
            self.SPECIAL_CHARS.search(s) is not None
            or self.LOOKS_LIKE_LITERAL.match(s) is not None
            or s.startswith(" ")
            or s.endswith(" ")
            or s.startswith("-")
        )

        if needs_quote:
            # Escape backslashes and quotes
            s = s.replace("\\", "\\\\").replace('"', '\\"')
            s = s.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
            return f'"{s}"'

        return s

    def generate_compact(self, project: ProjectInfo) -> str:
        """Generate minimal TOON output."""
        return self.generate(project, detail="compact")

    def generate_full(self, project: ProjectInfo) -> str:
        """Generate detailed TOON output."""
        return self.generate(project, detail="full")

    def generate_schema(self, format_type: str = "standard") -> str:
        """
        Generate JSON Schema for the TOON format.

        Args:
            format_type: 'standard', 'compact', 'ultra_compact' - determines format variant

        Returns:
            JSON Schema as string
        """
        import json

        base_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Code2Logic TOON Schema",
            "description": "Schema for Code2Logic TOON (Token-Oriented Object Notation) format",
            "type": "object",
        }

        if format_type == "ultra_compact":
            # Ultra-compact schema
            base_schema.update(
                {
                    "properties": {
                        "M": {
                            "type": "array",
                            "description": "Modules as [path,lines] pairs",
                            "items": {
                                "type": "array",
                                "items": [
                                    {"type": "string", "description": "Module path"},
                                    {"type": "integer", "description": "Lines of code"},
                                ],
                                "minItems": 2,
                                "maxItems": 2,
                            },
                        },
                        "D": {
                            "type": "object",
                            "description": "Module details with compact keys",
                            "patternProperties": {
                                ".*": {
                                    "type": "object",
                                    "properties": {
                                        "i": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Compact imports (grouped)",
                                        },
                                        "e": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Exports",
                                        },
                                        "c": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Classes with inline method counts",
                                        },
                                        "f": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Functions with signatures",
                                        },
                                    },
                                }
                            },
                        },
                    }
                }
            )
        else:
            # Standard TOON schema
            base_schema.update(
                {
                    "properties": {
                        "project": {"type": "string", "description": "Project name"},
                        "root": {"type": "string", "description": "Root path"},
                        "generated": {
                            "type": "string",
                            "description": "Generation timestamp",
                        },
                        "stats": {
                            "type": "object",
                            "properties": {
                                "files": {"type": "integer"},
                                "lines": {"type": "integer"},
                                "languages": {
                                    "type": "string",
                                    "description": "Language stats as delimited string",
                                },
                            },
                        },
                        "modules": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "language": {"type": "string"},
                                    "lines": {"type": "integer"},
                                    "imports": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "exports": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "classes": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "bases": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                                "docstring": {"type": "string"},
                                                "properties": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                                "methods": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "name": {"type": "string"},
                                                            "signature": {
                                                                "type": "string"
                                                            },
                                                            "decorators": {
                                                                "type": "array",
                                                                "items": {
                                                                    "type": "string"
                                                                },
                                                            },
                                                            "async": {"type": "string"},
                                                            "lines": {
                                                                "type": "integer"
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    },
                                    "functions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "signature": {"type": "string"},
                                                "decorators": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                                "async": {"type": "string"},
                                                "lines": {"type": "integer"},
                                            },
                                        },
                                    },
                                    "function_docs": {
                                        "type": "object",
                                        "description": "Additional function documentation",
                                        "patternProperties": {".*": {"type": "string"}},
                                    },
                                },
                            },
                        },
                    }
                }
            )

        return json.dumps(base_schema, indent=2)

    def generate_ultra_compact(self, project: ProjectInfo) -> str:
        """
        Generate minimal TOON with abbreviated keys.

        Ultra-compact format for maximum token efficiency:
        - Single-letter keys (M=modules, D=details, i=imports, c=classes, f=functions)
        - No self in signatures
        - Inline method definitions
        - Grouped imports
        """
        lines = []

        # Header in one line
        langs = "/".join(f"{k}:{v}" for k, v in project.languages.items())
        lines.append(
            f"# {project.name} | {project.total_files}f {project.total_lines}L | {langs}"
        )
        lines.append(
            "# Keys: M=modules, D=details, i=imports, c=classes, f=functions, m=methods"
        )

        # Modules as compact list
        lines.append(f"M[{len(project.modules)}]:")
        for m in project.modules:
            lines.append(f"  {m.path},{m.lines_code}")

        # Details only for modules with content
        lines.append("D:")
        for m in project.modules:
            if not m.classes and not m.functions:
                continue

            lines.append(f"  {m.path}:")

            # Compact imports
            if m.imports:
                compact = compact_imports(m.imports[:10])
                lines.append(f"    i: {','.join(compact)}")

            # Compact exports
            if m.exports:
                lines.append(f"    e: {','.join(m.exports[:CONSTANT_8])}")

            # Classes inline
            for c in m.classes[:CONSTANT_5]:
                methods_str = ",".join(
                    f"{meth.name}({len([p for p in meth.params if p not in ('self', 'cls')])})"
                    for meth in c.methods[:CONSTANT_5]
                )
                doc = (
                    truncate_docstring(c.docstring, CONSTANT_40) if c.docstring else ""
                )
                if doc:
                    lines.append(f"    {c.name}: {methods_str}  # {doc}")
                else:
                    lines.append(f"    {c.name}: {methods_str}")

            # Functions inline
            for f in m.functions[:CONSTANT_8]:
                sig = self._build_signature(f)
                lines.append(f"    {f.name}{sig}")

        return "\n".join(lines)


class TOONParser:
    """
    Parse TOON format back to Python dict.

    This is a simplified parser for code2logic TOON output.
    For full TOON parsing, use the official toon library.
    """

    def __init__(self):
        self.delimiter = ","

    def parse(self, content: str) -> Dict[str, Any]:
        """Parse TOON content to dict."""
        result = {}
        lines = content.split("\n")

        # Best-effort delimiter detection for arrays.
        # Note: in code2logic standard TOON, rows use ',' or '\t'.
        # '|' is used inside some cell values (e.g., decorators), so it must not be
        # treated as a delimiter.
        self.delimiter = "\t" if any("\t" in ln for ln in lines) else ","

        import csv

        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1

            if not line.strip() or line.strip().startswith("#"):
                continue

            # Parse key-value
            line = line.strip()

            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Check for array header
            array_match = re.match(r"(\w+)\[(\d+)\](\{[^}]+\})?", key)
            if array_match:
                arr_name = array_match.group(1)
                arr_len = int(array_match.group(2))
                fields = array_match.group(CONSTANT_3)

                if fields:
                    # Tabular array
                    field_names = fields[1:-1].split(",")
                    items = []

                    # Parse rows
                    for _ in range(arr_len):
                        if i >= len(lines):
                            break
                        row_line = lines[i].strip()
                        i += 1

                        if row_line:
                            row_values = next(
                                csv.reader(
                                    [row_line],
                                    delimiter=self.delimiter,
                                    quotechar='"',
                                    escapechar="\\",
                                )
                            )
                            item = {}
                            for fi, fn in enumerate(field_names):
                                if fi < len(row_values):
                                    item[fn.strip()] = self._parse_value(
                                        row_values[fi].strip()
                                    )
                            items.append(item)

                    result[arr_name] = items
                else:
                    # Primitive array
                    if value:
                        parts = next(
                            csv.reader(
                                [value],
                                delimiter=self.delimiter,
                                quotechar='"',
                                escapechar="\\",
                            )
                        )
                        items = [self._parse_value(v.strip()) for v in parts]
                        result[arr_name] = items
                    else:
                        result[arr_name] = []
            else:
                # Simple key-value
                result[key] = self._parse_value(value)

        return result

    def _parse_value(self, value: str) -> Any:
        """Parse a TOON value to Python type."""
        if not value:
            return ""

        # Unquote if quoted
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
            value = value.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
            value = value.replace('\\"', '"').replace("\\\\", "\\")
            return value

        # Check literals
        if value == "null":
            return None
        if value == "true":
            return True
        if value == "false":
            return False

        # Try number
        try:
            if "." in value or "e" in value.lower():
                return float(value)
            return int(value)
        except ValueError:
            pass

        return value


def generate_toon(
    project: ProjectInfo, detail: str = "standard", use_tabs: bool = False
) -> str:
    """
    Convenience function to generate TOON format.

    Args:
        project: Analyzed project info
        detail: Level of detail ('compact', 'standard', 'full')
        use_tabs: Use tab delimiter for better token efficiency

    Returns:
        TOON formatted string
    """
    gen = TOONGenerator(use_tabs=use_tabs)
    return gen.generate(project, detail)


def parse_toon(content: str) -> Dict[str, Any]:
    """Convenience function to parse TOON content."""
    return TOONParser().parse(content)
