"""
YAML Format Schema for Code2Logic.

Defines the structure and validation for YAML specifications.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class MethodSchema:
    """Schema for method definition."""

    name: str
    signature: str
    intent: str = ""
    lines: int = 0
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)
    raises: List[str] = field(default_factory=list)


@dataclass
class ClassSchema:
    """Schema for class definition."""

    name: str
    bases: List[str] = field(default_factory=list)
    docstring: str = ""
    methods: List[MethodSchema] = field(default_factory=list)
    properties: List[str] = field(default_factory=list)
    is_abstract: bool = False
    is_dataclass: bool = False


@dataclass
class FunctionSchema:
    """Schema for function definition."""

    name: str
    signature: str
    intent: str = ""
    lines: int = 0
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)


@dataclass
class ModuleSchema:
    """Schema for module definition."""

    path: str
    language: str = "python"
    lines: int = 0
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    classes: List[ClassSchema] = field(default_factory=list)
    functions: List[FunctionSchema] = field(default_factory=list)


@dataclass
class YAMLSchema:
    """
    Complete YAML specification schema.

    Structure:
    ```yaml
    project: <name>
    statistics:
      files: <int>
      lines: <int>
      languages: {<lang>: <count>}
    modules:
      - path: <path>
        language: <lang>
        imports: [<import>]
        classes:
          - name: <name>
            bases: [<base>]
            docstring: <doc>
            methods:
              - name: <name>
                signature: <sig>
                intent: <intent>
        functions:
          - name: <name>
            signature: <sig>
            intent: <intent>
    ```
    """

    project: str
    statistics: Dict[str, Any] = field(default_factory=dict)
    modules: List[ModuleSchema] = field(default_factory=list)


def validate_yaml(spec: str) -> Tuple[bool, List[str]]:
    """
    Validate YAML specification.

    Args:
        spec: YAML specification string

    Returns:
        Tuple of (is_valid, errors)
    """
    errors: List[str] = []

    try:
        import yaml
    except ImportError:
        return False, [
            "pyyaml is required for YAML validation. Install: pip install pyyaml"
        ]

    try:
        data = yaml.safe_load(spec)
    except Exception as e:
        return False, [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return False, ["Root must be a dictionary"]

    # Check required fields - support both traditional and compact formats
    required_fields = ["project", "modules", "meta", "defaults"]
    if not any(field in data for field in required_fields):
        errors.append("Missing required field (project, modules, meta, or defaults)")

    # Validate meta.legend if present
    if "meta" in data:
        if not isinstance(data["meta"], dict):
            errors.append("'meta' must be a dictionary")
        elif "legend" in data["meta"]:
            if not isinstance(data["meta"]["legend"], dict):
                errors.append("'meta.legend' must be a dictionary")
            else:
                # Validate that legend contains expected keys
                expected_legend_keys = [
                    "p",
                    "l",
                    "i",
                    "e",
                    "c",
                    "f",
                    "n",
                    "d",
                    "b",
                    "m",
                ]
                legend = data["meta"]["legend"]
                for key in expected_legend_keys:
                    if key not in legend:
                        errors.append(f"'meta.legend' missing expected key '{key}'")

    # Validate defaults if present
    if "defaults" in data:
        if not isinstance(data["defaults"], dict):
            errors.append("'defaults' must be a dictionary")

    # Validate modules
    if "modules" in data:
        if not isinstance(data["modules"], list):
            errors.append("'modules' must be a list")
        else:
            for i, module in enumerate(data["modules"]):
                module_errors = _validate_module(module, i)
                errors.extend(module_errors)

    return len(errors) == 0, errors


def _validate_module(module: Dict, index: int) -> List[str]:
    """Validate a module definition.

    Supports both full keys (path, classes, functions) and
    compact keys (p, c, f) for optimized YAML output.
    """
    errors: List[str] = []
    prefix = f"modules[{index}]"

    if not isinstance(module, dict):
        return [f"{prefix}: must be a dictionary"]

    # Support both 'path' and 'p' (compact key)
    if "path" not in module and "p" not in module:
        errors.append(f"{prefix}: missing 'path' or 'p'")

    # Validate classes - support both 'classes' and 'c' (compact key)
    classes_key = "classes" if "classes" in module else "c" if "c" in module else None
    if classes_key:
        if not isinstance(module[classes_key], list):
            errors.append(f"{prefix}.{classes_key}: must be a list")
        else:
            for j, cls in enumerate(module[classes_key]):
                cls_errors = _validate_class(cls, f"{prefix}.{classes_key}[{j}]")
                errors.extend(cls_errors)

    # Validate functions - support both 'functions' and 'f' (compact key)
    functions_key = (
        "functions" if "functions" in module else "f" if "f" in module else None
    )
    if functions_key:
        if not isinstance(module[functions_key], list):
            errors.append(f"{prefix}.{functions_key}: must be a list")

    return errors


def _validate_class(cls: Dict, prefix: str) -> List[str]:
    """Validate a class definition.

    Supports both full keys (name, methods) and
    compact keys (n, m) for optimized YAML output.
    """
    errors: List[str] = []

    if not isinstance(cls, dict):
        return [f"{prefix}: must be a dictionary"]

    # Support both 'name' and 'n' (compact key)
    if "name" not in cls and "n" not in cls:
        errors.append(f"{prefix}: missing 'name' or 'n'")

    # Validate methods - support both 'methods' and 'm' (compact key)
    methods_key = "methods" if "methods" in cls else "m" if "m" in cls else None
    if methods_key:
        if not isinstance(cls[methods_key], list):
            errors.append(f"{prefix}.{methods_key}: must be a list")
        else:
            for i, method in enumerate(cls[methods_key]):
                if not isinstance(method, dict):
                    errors.append(f"{prefix}.{methods_key}[{i}]: must be a dictionary")
                # Support both 'name' and 'n' for method names
                elif "name" not in method and "n" not in method:
                    errors.append(f"{prefix}.{methods_key}[{i}]: missing 'name' or 'n'")

    return errors
