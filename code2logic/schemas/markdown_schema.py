"""
Markdown Hybrid Format Schema for Code2Logic.

Combines YAML structure with Gherkin behaviors in Markdown.

Schema Structure:
```markdown
# Module: filename.py

## Metadata
- Language: python
- Lines: N
- Imports: module1, module2

## Classes

### ClassName
Base classes: BaseClass1, BaseClass2

**Attributes:**
- attr1: Type1
- attr2: Type2

**Methods:**

#### method_name
```yaml
signature: (params) -> ReturnType
async: false
```

```gherkin
Scenario: Method behavior
  Given precondition
  When action
  Then result
```

## Functions

### function_name
```yaml
signature: (params) -> ReturnType
```
```
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class MarkdownMethod:
    """Schema for Markdown method."""

    name: str
    signature: str = ""
    is_async: bool = False
    gherkin_scenarios: List[str] = field(default_factory=list)


@dataclass
class MarkdownClass:
    """Schema for Markdown class."""

    name: str
    bases: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    methods: List[MarkdownMethod] = field(default_factory=list)


@dataclass
class MarkdownModule:
    """Schema for Markdown module."""

    filename: str
    language: str = "python"
    lines: int = 0
    imports: List[str] = field(default_factory=list)
    classes: List[MarkdownClass] = field(default_factory=list)
    functions: List[MarkdownMethod] = field(default_factory=list)


@dataclass
class MarkdownSchema:
    """Complete Markdown specification schema."""

    modules: List[MarkdownModule] = field(default_factory=list)
    token_estimate: int = 0


def validate_markdown(spec: str) -> Tuple[bool, List[str]]:
    """
    Validate Markdown specification.

    Args:
        spec: Markdown specification string

    Returns:
        Tuple of (is_valid, errors)
    """
    errors: List[str] = []

    if not spec or not spec.strip():
        return False, ["Empty specification"]

    lines = spec.split("\n")

    # Check for module header
    has_module_header = False
    for line in lines[:10]:
        if line.startswith("# Module:") or line.startswith("# "):
            has_module_header = True
            break

    if not has_module_header:
        errors.append("Missing module header (# Module: filename)")

    # Check for code blocks
    in_code_block = False
    code_block_start = 0

    for i, line in enumerate(lines):
        if line.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_block_start = i
            else:
                in_code_block = False

    if in_code_block:
        errors.append(f"Unclosed code block starting at line {code_block_start + 1}")

    # Check for YAML blocks validity
    yaml_blocks = re.findall(r"```yaml\n(.*?)```", spec, re.DOTALL)
    for i, block in enumerate(yaml_blocks):
        try:
            import yaml

            yaml.safe_load(block)
        except Exception as e:
            errors.append(f"Invalid YAML in block {i + 1}: {e}")

    # Check for required sections
    has_classes = "## Classes" in spec or "### " in spec
    has_content = has_module_header or has_classes

    if not has_content:
        errors.append("Missing content sections")

    return len(errors) == 0, errors


def extract_markdown_sections(spec: str) -> Dict[str, Any]:
    """Extract sections from Markdown specification."""
    sections = {"metadata": {}, "classes": [], "functions": []}

    # Extract metadata
    metadata_match = re.search(r"## Metadata\n(.*?)(?=##|\Z)", spec, re.DOTALL)
    if metadata_match:
        metadata_text = metadata_match.group(1)
        for line in metadata_text.split("\n"):
            if ":" in line and line.startswith("-"):
                key, value = line[1:].split(":", 1)
                sections["metadata"][key.strip()] = value.strip()

    # Extract class names
    class_matches = re.findall(r"### (\w+)", spec)
    sections["classes"] = class_matches

    return sections
