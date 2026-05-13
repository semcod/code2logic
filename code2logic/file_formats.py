"""
File-specific format generators for better reproduction.

Generates detailed specifications for single files in various formats,
optimized for LLM code reproduction.
"""

import json
from pathlib import Path
from typing import Any, Dict


def generate_file_csv(file_path: Path) -> str:
    """Generate detailed CSV specification for a single file.

    Args:
        file_path: Path to source file

    Returns:
        CSV specification string
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    content = file_path.read_text()
    elements = _parse_file_elements(content)

    lines = ["type,name,parent,attributes,returns,docstring"]

    # Add imports
    for imp in elements["imports"][:10]:
        lines.append(f'import,"{imp}",,,')

    # Add classes and their attributes
    for cls in elements["classes"]:
        docstring = cls.get("docstring", "")[:50].replace('"', "'")
        lines.append(f'class,{cls["name"]},,,,"{docstring}"')

        for attr in cls.get("attributes", []):
            if isinstance(attr, dict):
                type_info = attr.get("type", "")
                default = attr.get("default", "")
                lines.append(
                    f'attribute,{attr["name"]},{cls["name"]},"{type_info}","{default}",'
                )
            else:
                lines.append(f"attribute,{attr},{cls['name']},,,")

        for method in cls.get("methods", []):
            if isinstance(method, dict):
                params = method.get("params", "")[:40]
                returns = method.get("returns", "")
                lines.append(
                    f'method,{method["name"]},{cls["name"]},"{params}","{returns}",'
                )
            else:
                lines.append(f"method,{method},{cls['name']},,,")

    # Add standalone functions
    for func in elements["functions"]:
        if isinstance(func, dict):
            params = func.get("params", "")[:40]
            returns = func.get("returns", "")
            lines.append(f'function,{func["name"]},,"{params}","{returns}",')
        else:
            lines.append(f"function,{func},,,")

    return "\n".join(lines)


def generate_file_json(file_path: Path) -> str:
    """Generate detailed JSON specification for a single file.

    Args:
        file_path: Path to source file

    Returns:
        JSON specification string
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    content = file_path.read_text()
    elements = _parse_file_elements(content)

    is_dataclass = "@dataclass" in content

    data = {
        "file": file_path.name,
        "module_docstring": elements["module_doc"][:200]
        if elements["module_doc"]
        else "",
        "imports": elements["imports"][:15],
        "is_dataclass_file": is_dataclass,
        "classes": [],
        "functions": [],
    }

    for cls in elements["classes"]:
        cls_data = {
            "name": cls["name"],
            "docstring": cls.get("docstring", "")[:100],
            "is_dataclass": is_dataclass,
            "attributes": [],
            "methods": [],
        }

        for attr in cls.get("attributes", []):
            if isinstance(attr, dict):
                cls_data["attributes"].append(
                    {
                        "name": attr["name"],
                        "type": attr.get("type", "Any"),
                        "default": attr.get("default", None),
                    }
                )
            else:
                cls_data["attributes"].append({"name": attr, "type": "Any"})

        for method in cls.get("methods", []):
            if isinstance(method, dict):
                cls_data["methods"].append(
                    {
                        "name": method["name"],
                        "params": method.get("params", ""),
                        "returns": method.get("returns", "None"),
                    }
                )
            else:
                cls_data["methods"].append({"name": method})

        data["classes"].append(cls_data)

    for func in elements["functions"]:
        if isinstance(func, dict):
            data["functions"].append(
                {
                    "name": func["name"],
                    "params": func.get("params", ""),
                    "returns": func.get("returns", "None"),
                }
            )
        else:
            data["functions"].append({"name": func})

    return json.dumps(data, indent=2)


def generate_file_yaml(file_path: Path) -> str:
    """Generate detailed YAML specification for a single file.

    Args:
        file_path: Path to source file

    Returns:
        YAML specification string
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    content = file_path.read_text()
    elements = _parse_file_elements(content)

    is_dataclass = "@dataclass" in content

    lines = [
        f"# YAML specification for {file_path.name}",
        f"file: {file_path.name}",
        f"type: {'dataclass_module' if is_dataclass else 'module'}",
        "",
        "imports:",
    ]

    for imp in elements["imports"][:10]:
        lines.append(f"  - {imp}")

    if elements["classes"]:
        lines.append("")
        lines.append("classes:")

        for cls in elements["classes"]:
            lines.append(f"  - name: {cls['name']}")
            if cls.get("docstring"):
                lines.append(f'    docstring: "{cls["docstring"][:60]}"')
            lines.append(f"    is_dataclass: {str(is_dataclass).lower()}")

            if cls.get("attributes"):
                lines.append("    attributes:")
                for attr in cls["attributes"]:
                    if isinstance(attr, dict):
                        lines.append(f"      - name: {attr['name']}")
                        if attr.get("type"):
                            lines.append(f"        type: {attr['type']}")
                        if attr.get("default"):
                            lines.append(f"        default: {attr['default']}")
                    else:
                        lines.append(f"      - name: {attr}")

            if cls.get("methods"):
                lines.append("    methods:")
                for method in cls["methods"]:
                    if isinstance(method, dict):
                        lines.append(f"      - name: {method['name']}")
                        if method.get("params"):
                            lines.append(f'        params: "{method["params"][:50]}"')
                        if method.get("returns"):
                            lines.append(f"        returns: {method['returns']}")
                    else:
                        lines.append(f"      - name: {method}")

    if elements["functions"]:
        lines.append("")
        lines.append("functions:")

        for func in elements["functions"]:
            if isinstance(func, dict):
                lines.append(f"  - name: {func['name']}")
                if func.get("params"):
                    lines.append(f'    params: "{func["params"][:60]}"')
                if func.get("returns"):
                    lines.append(f"    returns: {func['returns']}")
            else:
                lines.append(f"  - name: {func}")

    return "\n".join(lines)


def _parse_file_elements(content: str) -> Dict[str, Any]:
    """Parse file content to extract code elements.

    Args:
        content: Source file content

    Returns:
        Dictionary with imports, classes, functions, module_doc
    """
    classes = []
    functions = []
    imports = []
    module_doc = ""

    lines = content.split("\n")
    in_class = None
    in_docstring = False
    in_class_docstring = False
    docstring_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Module docstring
        if i < 5 and stripped.startswith('"""') and not module_doc:
            if stripped.count('"""') >= 2:
                module_doc = stripped.strip('"""').strip()
            else:
                in_docstring = True
                docstring_lines = [stripped.lstrip('"""')]
                continue

        if in_docstring and not in_class:
            if '"""' in stripped:
                docstring_lines.append(stripped.rstrip('"""'))
                module_doc = " ".join(docstring_lines)[:200]
                in_docstring = False
            else:
                docstring_lines.append(stripped)
            continue

        # Class docstring
        if in_class_docstring:
            if '"""' in stripped:
                docstring_lines.append(stripped.rstrip('"""'))
                class_docstring = " ".join(docstring_lines)[:150]
                classes[-1]["docstring"] = class_docstring
                in_class_docstring = False
            else:
                docstring_lines.append(stripped)
            continue

        # Imports
        if stripped.startswith("from ") or stripped.startswith("import "):
            imports.append(stripped)

        # Classes
        if stripped.startswith("class "):
            class_name = stripped.split("(")[0].split(":")[0].replace("class ", "")
            in_class = class_name
            classes.append(
                {"name": class_name, "attributes": [], "methods": [], "docstring": ""}
            )

        # Class docstring start
        if (
            in_class
            and stripped.startswith('"""')
            and classes
            and not classes[-1].get("docstring")
        ):
            if stripped.count('"""') >= 2:
                classes[-1]["docstring"] = stripped.strip('"""').strip()[:100]
            else:
                in_class_docstring = True
                docstring_lines = [stripped.lstrip('"""')]
            continue

        # Class attributes
        if (
            in_class
            and ":" in stripped
            and not stripped.startswith("def ")
            and not stripped.startswith("#")
        ):
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if any(
                stripped.startswith(x)
                for x in ["Attributes", "-", "Args", "Returns", "Raises"]
            ):
                continue
            if any(x in stripped.lower() for x in ["path to", "the ", "a ", "an "]):
                continue

            attr_full = stripped
            if attr_full and not attr_full.startswith("return"):
                attr_name = attr_full.split(":")[0].strip()
                if (
                    attr_name
                    and attr_name.isidentifier()
                    and attr_name
                    not in ["try", "if", "for", "while", "class", "def", "return"]
                ):
                    existing = [
                        a.get("name") if isinstance(a, dict) else a
                        for a in classes[-1]["attributes"]
                    ]
                    if attr_name not in existing:
                        # Parse type and default
                        type_part = ""
                        default_part = ""
                        if ":" in attr_full:
                            after_colon = attr_full.split(":", 1)[1].strip()
                            if "=" in after_colon:
                                type_part = after_colon.split("=")[0].strip()
                                default_part = after_colon.split("=", 1)[1].strip()
                            else:
                                type_part = after_colon

                        classes[-1]["attributes"].append(
                            {
                                "name": attr_name,
                                "type": type_part,
                                "default": default_part,
                            }
                        )

        # Functions/methods
        if stripped.startswith("def "):
            func_line = stripped
            if func_line.endswith(":"):
                func_line = func_line[:-1]
            func_name = func_line.split("(")[0].replace("def ", "")

            try:
                params_part = func_line.split("(", 1)[1].rsplit(")", 1)[0]
                return_part = (
                    func_line.split("->")[-1].strip() if "->" in func_line else "None"
                )
            except (IndexError, ValueError):
                params_part = ""
                return_part = "None"

            func_info = {
                "name": func_name,
                "params": params_part,
                "returns": return_part,
            }

            if in_class and classes:
                classes[-1]["methods"].append(func_info)
            else:
                functions.append(func_info)

    return {
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "module_doc": module_doc,
    }
