"""
JSON Format Schema for Code2Logic.

Defines the structure and validation for JSON specifications.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class JSONMethodSchema:
    """Schema for JSON method definition."""

    name: str
    signature: str = ""
    intent: str = ""
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)
    params: List[str] = field(default_factory=list)
    return_type: str = "None"


@dataclass
class JSONClassSchema:
    """Schema for JSON class definition."""

    name: str
    bases: List[str] = field(default_factory=list)
    docstring: str = ""
    methods: List[JSONMethodSchema] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    is_abstract: bool = False
    is_dataclass: bool = False


@dataclass
class JSONFunctionSchema:
    """Schema for JSON function definition."""

    name: str
    signature: str = ""
    intent: str = ""
    is_async: bool = False
    params: List[str] = field(default_factory=list)
    return_type: str = "None"


@dataclass
class JSONModuleSchema:
    """Schema for JSON module definition."""

    path: str
    language: str = "python"
    lines: int = 0
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    classes: List[JSONClassSchema] = field(default_factory=list)
    functions: List[JSONFunctionSchema] = field(default_factory=list)


@dataclass
class JSONSchema:
    """
    Complete JSON specification schema.

    Structure:
    ```json
    {
      "project": "<name>",
      "statistics": {
        "files": <int>,
        "lines": <int>,
        "languages": {"python": <count>}
      },
      "modules": [
        {
          "path": "<path>",
          "language": "<lang>",
          "imports": ["<import>"],
          "classes": [
            {
              "name": "<name>",
              "bases": ["<base>"],
              "docstring": "<doc>",
              "methods": [
                {
                  "name": "<name>",
                  "signature": "<sig>",
                  "intent": "<intent>",
                  "is_async": false
                }
              ]
            }
          ],
          "functions": [
            {
              "name": "<name>",
              "signature": "<sig>",
              "intent": "<intent>"
            }
          ]
        }
      ]
    }
    ```
    """

    project: str = ""
    statistics: Dict[str, Any] = field(default_factory=dict)
    modules: List[JSONModuleSchema] = field(default_factory=list)


def validate_json(spec: str) -> Tuple[bool, List[str]]:
    """
    Validate JSON specification.

    Args:
        spec: JSON specification string

    Returns:
        Tuple of (is_valid, errors)
    """
    errors: List[str] = []

    try:
        data = json.loads(spec)
    except json.JSONDecodeError as e:
        return False, [f"JSON parse error: {e}"]

    if not isinstance(data, dict):
        return False, ["Root must be an object"]

    # Check for required fields
    if "project" not in data and "modules" not in data:
        errors.append("Missing 'project' or 'modules' field")

    # Validate modules
    if "modules" in data:
        if not isinstance(data["modules"], list):
            errors.append("'modules' must be an array")
        else:
            for i, module in enumerate(data["modules"]):
                module_errors = _validate_json_module(module, i)
                errors.extend(module_errors)

    return len(errors) == 0, errors


def _validate_json_module(module: Dict, index: int) -> List[str]:
    """Validate a JSON module definition."""
    errors: List[str] = []
    prefix = f"modules[{index}]"

    if not isinstance(module, dict):
        return [f"{prefix}: must be an object"]

    if "path" not in module:
        errors.append(f"{prefix}: missing 'path'")

    # Validate classes
    if "classes" in module:
        if not isinstance(module["classes"], list):
            errors.append(f"{prefix}.classes: must be an array")
        else:
            for j, cls in enumerate(module["classes"]):
                cls_errors = _validate_json_class(cls, f"{prefix}.classes[{j}]")
                errors.extend(cls_errors)

    # Validate functions
    if "functions" in module:
        if not isinstance(module["functions"], list):
            errors.append(f"{prefix}.functions: must be an array")

    return errors


def _validate_json_class(cls: Dict, prefix: str) -> List[str]:
    """Validate a JSON class definition."""
    errors: List[str] = []

    if not isinstance(cls, dict):
        return [f"{prefix}: must be an object"]

    if "name" not in cls:
        errors.append(f"{prefix}: missing 'name'")

    # Validate methods
    if "methods" in cls:
        if not isinstance(cls["methods"], list):
            errors.append(f"{prefix}.methods: must be an array")
        else:
            for i, method in enumerate(cls["methods"]):
                if not isinstance(method, dict):
                    errors.append(f"{prefix}.methods[{i}]: must be an object")
                elif "name" not in method:
                    errors.append(f"{prefix}.methods[{i}]: missing 'name'")

    return errors


def parse_json_spec(spec: str) -> Optional[JSONSchema]:
    """
    Parse JSON specification into schema.

    Args:
        spec: JSON specification string

    Returns:
        JSONSchema or None if invalid
    """
    try:
        data = json.loads(spec)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    schema = JSONSchema(
        project=data.get("project", ""),
        statistics=data.get("statistics", {}),
    )

    for module_data in data.get("modules", []):
        module = JSONModuleSchema(
            path=module_data.get("path", ""),
            language=module_data.get("language", "python"),
            lines=module_data.get("lines", 0),
            imports=module_data.get("imports", []),
            exports=module_data.get("exports", []),
        )

        for cls_data in module_data.get("classes", []):
            cls = JSONClassSchema(
                name=cls_data.get("name", ""),
                bases=cls_data.get("bases", []),
                docstring=cls_data.get("docstring", ""),
            )
            for method_data in cls_data.get("methods", []):
                method = JSONMethodSchema(
                    name=method_data.get("name", ""),
                    signature=method_data.get("signature", ""),
                    intent=method_data.get("intent", ""),
                    is_async=method_data.get("is_async", False),
                )
                cls.methods.append(method)
            module.classes.append(cls)

        for func_data in module_data.get("functions", []):
            func = JSONFunctionSchema(
                name=func_data.get("name", ""),
                signature=func_data.get("signature", ""),
                intent=func_data.get("intent", ""),
                is_async=func_data.get("is_async", False),
            )
            module.functions.append(func)

        schema.modules.append(module)

    return schema
