"""
LogicML Format Schema for Code2Logic.

LogicML is optimized for LLM code reproduction with:
- Minimal tokens, maximum information
- Precise signatures with types
- Inline behavior descriptions
- Edge cases and side effects

Schema Structure:
```yaml
# filename | ClassName | N lines

imports:
  stdlib: [module1, module2]
  third_party: [package1]
  local: [.module]

ClassName:
  doc: "Description"
  bases: [BaseClass]
  # Pydantic model - use Field() for attributes
  attrs:
    attr_name: type
  methods:
    method_name:
      sig: (params) -> ReturnType
      sig: async (params) -> ReturnType
      sig: @property (self) -> Type
      does: "Docstring"
      edge: "condition → action"
      side: "Side effect description"

functions:
  func_name:
    sig: (params) -> ReturnType
    does: "Description"

# Re-export module
type: re-export
exports:
  - Name1
  - Name2
```
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LogicMLMethod:
    """Schema for LogicML method."""

    name: str
    signature: str
    does: str = ""
    edge: List[str] = field(default_factory=list)
    side: str = ""
    is_async: bool = False
    is_property: bool = False


@dataclass
class LogicMLClass:
    """Schema for LogicML class."""

    name: str
    doc: str = ""
    bases: List[str] = field(default_factory=list)
    attrs: Dict[str, str] = field(default_factory=dict)
    methods: List[LogicMLMethod] = field(default_factory=list)
    is_pydantic: bool = False
    is_enum: bool = False
    is_dataclass: bool = False


@dataclass
class LogicMLModule:
    """Schema for LogicML module."""

    filename: str
    lines: int = 0
    classes: List[str] = field(default_factory=list)
    imports: Dict[str, List[str]] = field(default_factory=dict)
    module_classes: List[LogicMLClass] = field(default_factory=list)
    functions: List[LogicMLMethod] = field(default_factory=list)
    module_type: str = "standard"  # standard, re-export, index
    exports: List[str] = field(default_factory=list)


@dataclass
class LogicMLSchema:
    """
    Complete LogicML specification schema.

    Design Principles:
    1. Minimal tokens - 40% better than YAML
    2. Precise signatures with full type hints
    3. Inline behavior descriptions (no verbose Gherkin)
    4. Edge cases as compact rules
    5. Side effects explicitly noted
    """

    modules: List[LogicMLModule] = field(default_factory=list)

    # Metrics
    token_estimate: int = 0
    file_count: int = 0
    class_count: int = 0
    function_count: int = 0


def validate_logicml(spec: str) -> Tuple[bool, List[str]]:
    """
    Validate LogicML specification.

    Args:
        spec: LogicML specification string

    Returns:
        Tuple of (is_valid, errors)
    """
    errors: List[str] = []

    if not spec or not spec.strip():
        return False, ["Empty specification"]

    lines = spec.split("\n")

    # Check for header comment
    has_header = False
    for line in lines[:5]:
        if line.startswith("#") and "|" in line:
            has_header = True
            break

    if not has_header:
        errors.append("Missing header comment (# filename | class | N lines)")

    # Validate structure
    in_methods = False
    in_attrs = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Check for class definition
        if re.match(r"^[A-Z][a-zA-Z0-9_]*:$", stripped):
            in_methods = False
            in_attrs = False
            continue

        # Check for section headers
        if stripped == "methods:":
            in_methods = True
            in_attrs = False
            continue
        elif stripped == "attrs:":
            in_attrs = True
            in_methods = False
            continue
        elif stripped == "functions:":
            in_methods = False
            in_attrs = False
            continue
        elif stripped == "imports:":
            continue
        elif stripped == "exports:":
            continue

        # Validate method signatures
        if in_methods and "sig:" in stripped:
            sig_match = re.search(r"sig:\s*(.+)", stripped)
            if sig_match:
                sig = sig_match.group(1)
                # Check for balanced parentheses
                if sig.count("(") != sig.count(")"):
                    errors.append(
                        f"Line {i + 1}: Unbalanced parentheses in signature: {sig}"
                    )
                # Check for return type
                if "->" not in sig and not sig.startswith("@property"):
                    errors.append(
                        f"Line {i + 1}: Missing return type in signature: {sig}"
                    )

        # Validate attrs
        if in_attrs and ":" in stripped and not stripped.endswith(":"):
            parts = stripped.split(":")
            if len(parts) < 2:
                errors.append(f"Line {i + 1}: Invalid attribute format: {stripped}")

    # Check for required elements
    has_content = any(
        line.strip() and not line.strip().startswith("#") for line in lines
    )

    if not has_content:
        errors.append("No content found in specification")

    return len(errors) == 0, errors


def parse_logicml_header(line: str) -> Optional[Dict[str, Any]]:
    """Parse LogicML header comment."""
    # Format: # filename | ClassName, Class2 | N lines
    match = re.match(r"#\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*lines?", line)
    if match:
        return {
            "filename": match.group(1).strip(),
            "classes": [c.strip() for c in match.group(2).split(",")],
            "lines": int(match.group(3)),
        }
    return None


def extract_logicml_signature(sig_line: str) -> Dict[str, Any]:
    """Extract signature components from LogicML sig: line."""
    result = {
        "is_async": False,
        "is_property": False,
        "params": [],
        "return_type": "None",
    }

    sig = sig_line.strip()
    if sig.startswith("sig:"):
        sig = sig[4:].strip()

    if sig.startswith("async"):
        result["is_async"] = True
        sig = sig[5:].strip()

    if sig.startswith("@property"):
        result["is_property"] = True
        sig = sig[9:].strip()

    # Extract params and return type
    match = re.match(r"\(([^)]*)\)\s*->\s*(.+)", sig)
    if match:
        params_str = match.group(1)
        result["params"] = [p.strip() for p in params_str.split(",") if p.strip()]
        result["return_type"] = match.group(2).strip()

    return result
