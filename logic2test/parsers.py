"""
Parsers for Code2Logic output formats (YAML, Hybrid, TOON).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class FunctionSpec:
    """Specification of a function/method extracted from logic file."""

    name: str
    signature: str
    params: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    is_async: bool = False
    is_method: bool = False
    class_name: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    module_path: str = ""


@dataclass
class ClassSpec:
    """Specification of a class extracted from logic file."""

    name: str
    bases: List[str] = field(default_factory=list)
    methods: List[FunctionSpec] = field(default_factory=list)
    attributes: List[Dict[str, str]] = field(default_factory=list)
    is_dataclass: bool = False
    fields: List[Dict[str, Any]] = field(default_factory=list)
    docstring: Optional[str] = None
    module_path: str = ""


@dataclass
class ModuleSpec:
    """Specification of a module extracted from logic file."""

    path: str
    language: str = "python"
    classes: List[ClassSpec] = field(default_factory=list)
    functions: List[FunctionSpec] = field(default_factory=list)
    constants: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)


@dataclass
class ProjectSpec:
    """Full project specification from logic file."""

    name: str
    modules: List[ModuleSpec] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0


class LogicParser:
    """Parser for Code2Logic output formats."""

    def __init__(self, file_path: Union[str, Path]):
        self.file_path = Path(file_path)
        self.content = self.file_path.read_text(encoding="utf-8")
        self.data: Dict[str, Any] = {}
        self.format: str = "unknown"

    def parse(self) -> ProjectSpec:
        """Parse the logic file and return ProjectSpec."""
        self._detect_and_parse_format()
        return self._build_project_spec()

    def _detect_and_parse_format(self) -> None:
        """Detect format (YAML/Hybrid/TOON) and parse."""
        content = self.content.strip()

        # Try YAML first
        if content.startswith("header:") or content.startswith("project:"):
            self._parse_yaml()
        elif content.startswith("M:") or "\nM:" in content[:200]:
            self._parse_yaml()  # Hybrid is also YAML
        else:
            # Try TOON format
            self._parse_toon()

    def _parse_yaml(self) -> None:
        """Parse YAML or Hybrid YAML format."""
        try:
            import yaml

            self.data = yaml.safe_load(self.content)
            self.format = "hybrid" if "M" in self.data else "yaml"
        except ImportError:
            self._parse_yaml_simple()
        except Exception as e:
            raise ValueError(f"Failed to parse YAML: {e}")

    def _parse_yaml_simple(self) -> None:
        """Simple YAML parser without pyyaml dependency."""
        self.data = {"modules": [], "header": {}}
        self.format = "yaml"

        lines = self.content.split("\n")
        current_module = None
        current_class = None
        current_func = None
        indent_stack = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            if stripped.startswith("project:"):
                self.data["header"]["project"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- p:") or stripped.startswith("- path:"):
                path = stripped.split(":", 1)[1].strip()
                current_module = {"p": path, "c": [], "f": []}
                self.data.setdefault("modules", []).append(current_module)
                current_class = None
            elif stripped.startswith("- n:") or stripped.startswith("- name:"):
                name = stripped.split(":", 1)[1].strip()
                if current_module and indent > 4:
                    # Could be class or function
                    if "c:" in str(indent_stack) or "classes:" in str(indent_stack):
                        current_class = {"n": name, "m": [], "attrs": []}
                        current_module.setdefault("c", []).append(current_class)
                    else:
                        func = {"n": name, "sig": "()"}
                        if current_class:
                            current_class.setdefault("m", []).append(func)
                        else:
                            current_module.setdefault("f", []).append(func)
            elif stripped.startswith("sig:") or stripped.startswith("signature:"):
                sig = stripped.split(":", 1)[1].strip()
                if current_func:
                    current_func["sig"] = sig

    def _parse_toon(self) -> None:
        """Parse TOON format."""
        self.format = "toon"
        self.data = {"modules": [], "header": {}}

        lines = self.content.strip().split("\n")
        current_module = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Header line: project:name files:N lines:N
            if line.startswith("project:"):
                parts = line.split()
                for part in parts:
                    if part.startswith("project:"):
                        self.data["header"]["project"] = part.split(":", 1)[1]
                    elif part.startswith("files:"):
                        self.data["header"]["files"] = int(part.split(":", 1)[1])
                continue

            # Module line: M path:lines or path.py:123
            if line.startswith("M ") or "/" in line or line.endswith(".py"):
                path = line.lstrip("M ").split(":")[0].strip()
                current_module = {"p": path, "c": [], "f": []}
                self.data["modules"].append(current_module)
                continue

            # Class line: C ClassName or  C:ClassName
            if line.startswith("C ") or line.startswith("C:"):
                name = line.lstrip("C ").lstrip("C:").split(":")[0].strip()
                cls = {"n": name, "m": [], "attrs": []}
                if current_module:
                    current_module["c"].append(cls)
                continue

            # Function line: F func_name(params) or def func_name
            if line.startswith("F ") or line.startswith("def "):
                match = re.match(r"(?:F |def )(\w+)\s*(\([^)]*\))?", line)
                if match:
                    name = match.group(1)
                    sig = match.group(2) or "()"
                    func = {"n": name, "sig": sig}
                    if current_module:
                        current_module["f"].append(func)

    def _build_project_spec(self) -> ProjectSpec:
        """Build ProjectSpec from parsed data."""
        header = self.data.get("header", {})
        project_name = header.get("project", self.file_path.stem)

        modules = []
        for mod_data in self.data.get("modules", []):
            module = self._build_module_spec(mod_data)
            modules.append(module)

        return ProjectSpec(
            name=project_name,
            modules=modules,
            total_files=header.get("files", len(modules)),
            total_lines=header.get("lines", 0),
        )

    def _build_module_spec(self, mod_data: Dict) -> ModuleSpec:
        """Build ModuleSpec from module data."""
        path = mod_data.get("p", mod_data.get("path", ""))
        language = mod_data.get("lang", mod_data.get("language", "python"))

        classes = []
        for cls_data in mod_data.get("c", mod_data.get("classes", [])):
            cls = self._build_class_spec(cls_data, path)
            classes.append(cls)

        functions = []
        for func_data in mod_data.get("f", mod_data.get("functions", [])):
            func = self._build_function_spec(func_data, path)
            functions.append(func)

        constants = mod_data.get("const", mod_data.get("constants", []))
        imports = mod_data.get("i", mod_data.get("imports", []))

        return ModuleSpec(
            path=path,
            language=language,
            classes=classes,
            functions=functions,
            constants=constants,
            imports=imports if isinstance(imports, list) else [],
        )

    def _build_class_spec(self, cls_data: Dict, module_path: str) -> ClassSpec:
        """Build ClassSpec from class data."""
        name = cls_data.get("n", cls_data.get("name", ""))
        bases = cls_data.get("b", cls_data.get("bases", []))
        docstring = cls_data.get("d", cls_data.get("docstring", ""))
        is_dataclass = cls_data.get("dataclass", False) or "dataclass" in cls_data.get("dec", [])
        fields = cls_data.get("fields", [])
        attrs = cls_data.get("attrs", cls_data.get("attributes", []))

        methods = []
        for meth_data in cls_data.get("m", cls_data.get("methods", [])):
            meth = self._build_function_spec(
                meth_data, module_path, is_method=True, class_name=name
            )
            methods.append(meth)

        return ClassSpec(
            name=name,
            bases=bases if isinstance(bases, list) else [],
            methods=methods,
            attributes=attrs if isinstance(attrs, list) else [],
            is_dataclass=is_dataclass,
            fields=fields if isinstance(fields, list) else [],
            docstring=docstring,
            module_path=module_path,
        )

    def _build_function_spec(
        self,
        func_data: Dict,
        module_path: str,
        is_method: bool = False,
        class_name: Optional[str] = None,
    ) -> FunctionSpec:
        """Build FunctionSpec from function data."""
        name = func_data.get("n", func_data.get("name", ""))
        sig = func_data.get("sig", func_data.get("signature", "()"))
        docstring = func_data.get("d", func_data.get("intent", func_data.get("docstring", "")))
        is_async = func_data.get("async", False)
        decorators = func_data.get("dec", func_data.get("decorators", []))
        return_type = func_data.get("ret", func_data.get("return_type", None))

        # Parse params from signature
        params = self._parse_params_from_sig(sig)

        return FunctionSpec(
            name=name,
            signature=sig,
            params=params,
            return_type=return_type,
            docstring=docstring,
            is_async=is_async,
            is_method=is_method,
            class_name=class_name,
            decorators=decorators if isinstance(decorators, list) else [],
            module_path=module_path,
        )

    def _parse_params_from_sig(self, sig: str) -> List[str]:
        """Parse parameter names from signature string."""
        if not sig or sig == "()":
            return []

        # Extract content between parentheses
        match = re.search(r"\(([^)]*)\)", sig)
        if not match:
            return []

        params_str = match.group(1).strip()
        if not params_str:
            return []

        # Split by comma, handling nested brackets
        params = []
        depth = 0
        current = []
        for char in params_str:
            if char in "([{<":
                depth += 1
            elif char in ")]}>":
                depth -= 1
            if char == "," and depth == 0:
                param = "".join(current).strip()
                if param and not param.startswith("..."):
                    # Extract just the name
                    name = param.split(":")[0].split("=")[0].strip()
                    name = name.lstrip("*")
                    if name and name not in ("self", "cls"):
                        params.append(name)
                current = []
            else:
                current.append(char)

        # Last param
        if current:
            param = "".join(current).strip()
            if param and not param.startswith("..."):
                name = param.split(":")[0].split("=")[0].strip()
                name = name.lstrip("*")
                if name and name not in ("self", "cls"):
                    params.append(name)

        return params
