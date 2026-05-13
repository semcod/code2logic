"""
Shared utilities for Code2Logic generators.

Provides common functions used across multiple generators
to reduce code duplication and ensure consistency.

Key Legend (for LLM transparency):
- compact_imports: Groups imports like typing.{Dict,List}
- abbreviate_type: Shortens types (str->s, Dict->D)
- build_signature: Creates compact signatures without self
- categorize_function: Classifies functions (read/create/update/delete)
- truncate_docstring: Limits docstrings to first sentence
"""

import hashlib
import re
from typing import Dict, List, Optional, Set

# ============================================================================
# Import Handling
# ============================================================================


def compact_imports(imports: List[str], max_items: int = 10) -> List[str]:
    """
    Compact imports by grouping submodules.

    Example:
        ['typing', 'typing.Dict', 'typing.List'] -> ['typing.{Dict,List}']

    Args:
        imports: List of import strings
        max_items: Maximum number of items to return

    Returns:
        Compacted import list
    """
    if not imports:
        return []

    groups: Dict[str, Set[str]] = {}
    standalone: List[str] = []

    for imp in imports[: max_items * 2]:  # Process more to allow grouping
        if "." in imp:
            base, sub = imp.rsplit(".", 1)
            # Skip duplicates like module.module
            if base != sub:
                if base not in groups:
                    groups[base] = set()
                groups[base].add(sub)
        else:
            if imp not in standalone:
                standalone.append(imp)

    result = standalone.copy()
    for base, subs in sorted(groups.items()):
        if len(subs) == 1:
            result.append(f"{base}.{list(subs)[0]}")
        elif len(subs) <= 5:
            result.append(f"{base}.{{{','.join(sorted(subs))}}}")
        else:
            # Too many - just list base
            result.append(base)

    return result[:max_items]


def deduplicate_imports(imports: List[str]) -> List[str]:
    """
    Remove redundant imports.

    Example:
        ['typing', 'typing.Dict'] -> ['typing.Dict']

    Args:
        imports: List of import strings

    Returns:
        Deduplicated import list
    """
    if not imports:
        return []

    seen_bases: Set[str] = set()
    result: List[str] = []

    # Sort by specificity (more dots = more specific)
    sorted_imports = sorted(imports, key=lambda x: -x.count("."))

    for imp in sorted_imports:
        base = imp.split(".")[0]
        # If we have a more specific import, skip the base
        if imp == base and base in seen_bases:
            continue
        result.append(imp)
        seen_bases.add(base)

    return result


# ============================================================================
# Type Abbreviations
# ============================================================================

# Mapping: full type -> abbreviated type
# Used to reduce token count in specifications
TYPE_ABBREVIATIONS = {
    "str": "s",
    "int": "i",
    "bool": "b",
    "float": "f",
    "None": "N",
    "Any": "A",
    "List": "L",
    "Dict": "D",
    "Set": "S",
    "Tuple": "T",
    "Optional": "?",
    "Callable": "Fn",
    "Union": "U",
    "Sequence": "Seq",
    "Mapping": "Map",
    "Iterable": "Iter",
}


def abbreviate_type(type_str: str) -> str:
    """
    Abbreviate type annotations for compactness.

    Example:
        'Dict[str, Any]' -> 'D[s,A]'
        'Optional[List[str]]' -> '?[L[s]]'

    Args:
        type_str: Full type annotation string

    Returns:
        Abbreviated type string
    """
    if not type_str:
        return ""

    result = type_str
    for full, short in TYPE_ABBREVIATIONS.items():
        result = result.replace(full, short)
    # Remove spaces around brackets
    result = re.sub(r"\s*\[\s*", "[", result)
    result = re.sub(r"\s*\]\s*", "]", result)
    result = re.sub(r"\s*,\s*", ",", result)
    return result


def expand_type(abbrev: str) -> str:
    """
    Expand abbreviated type back to full form.

    Args:
        abbrev: Abbreviated type string

    Returns:
        Full type annotation string
    """
    if not abbrev:
        return ""

    result = abbrev
    # Reverse mapping (process longer abbreviations first)
    for full, short in sorted(TYPE_ABBREVIATIONS.items(), key=lambda x: -len(x[1])):
        result = result.replace(short, full)
    return result


# ============================================================================
# Signature Handling
# ============================================================================


def build_signature(
    params: List[str],
    return_type: Optional[str] = None,
    include_self: bool = False,
    abbreviate: bool = False,
    max_params: int = 6,
) -> str:
    """
    Build compact function signature.

    Args:
        params: List of parameter strings (e.g., ['self', 'name:str'])
        return_type: Return type annotation
        include_self: Whether to include self/cls (default: False)
        abbreviate: Whether to abbreviate types (default: False)
        max_params: Maximum parameters to include (default: 6)

    Returns:
        Signature string like "(param1,param2)->ReturnType"
    """
    clean_params = []
    for p in params[: max_params + 1]:  # +1 to account for self
        p_clean = p.replace("\n", " ").replace("  ", " ").strip()

        # Skip self/cls unless requested
        if p_clean in ("self", "cls") and not include_self:
            continue
        if p_clean.startswith("self:") and not include_self:
            continue

        # Abbreviate types if requested
        if abbreviate and ":" in p_clean:
            name, typ = p_clean.split(":", 1)
            typ = abbreviate_type(typ.strip())
            p_clean = f"{name.strip()}:{typ}"

        if p_clean:
            clean_params.append(p_clean)

    # Limit to max_params
    if len(clean_params) > max_params:
        overflow = len(params) - max_params - 1  # -1 for self
        clean_params = clean_params[:max_params]
        clean_params.append(f"...+{overflow}")

    params_str = ",".join(clean_params)

    ret = ""
    if return_type:
        ret_type = abbreviate_type(return_type) if abbreviate else return_type
        ret = f"->{ret_type}"

    return f"({params_str}){ret}"


def remove_self_from_params(params: List[str]) -> List[str]:
    """
    Remove 'self' and 'cls' from parameter list.

    Args:
        params: List of parameter strings

    Returns:
        Filtered parameter list
    """
    return [
        p
        for p in params
        if p.strip() not in ("self", "cls") and not p.strip().startswith("self:")
    ]


# ============================================================================
# Categorization
# ============================================================================

# Patterns for categorizing functions by name
# Used to help LLMs understand function purpose
CATEGORY_PATTERNS = {
    "read": ("get", "fetch", "find", "load", "read", "query", "retrieve", "list"),
    "create": ("create", "add", "insert", "new", "make", "build", "generate"),
    "update": ("update", "set", "modify", "edit", "patch", "change"),
    "delete": ("delete", "remove", "clear", "destroy", "drop"),
    "validate": ("validate", "check", "verify", "is_", "has_", "can_", "ensure"),
    "transform": ("convert", "transform", "parse", "format", "to_", "from_"),
    "lifecycle": ("init", "setup", "configure", "start", "stop", "close", "dispose"),
    "communicate": ("send", "emit", "notify", "publish", "broadcast"),
}


def categorize_function(name: str) -> str:
    """
    Categorize function by name pattern.

    Args:
        name: Function name (may include class prefix like 'Class.method')

    Returns:
        Category string: 'read', 'create', 'update', 'delete',
                        'validate', 'transform', 'lifecycle', 'communicate', 'other'
    """
    name_lower = name.lower().split(".")[-1]  # Handle method names

    for category, patterns in CATEGORY_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return category

    return "other"


# Domain keywords for extracting domain from file paths
DOMAIN_KEYWORDS = [
    "auth",
    "user",
    "order",
    "payment",
    "product",
    "cart",
    "config",
    "util",
    "api",
    "service",
    "model",
    "controller",
    "validation",
    "test",
    "generator",
    "parser",
    "llm",
    "db",
    "cache",
    "queue",
    "worker",
    "handler",
    "middleware",
]


def extract_domain(path: str) -> str:
    """
    Extract domain from file path.

    Args:
        path: File path string

    Returns:
        Domain string (e.g., 'auth', 'user', 'config')
    """
    parts = path.lower().replace("\\", "/").split("/")

    for part in parts:
        for domain in DOMAIN_KEYWORDS:
            if domain in part:
                return domain

    # Return parent folder name
    return parts[-2] if len(parts) > 1 else "root"


# ============================================================================
# Hashing
# ============================================================================


def compute_hash(name: str, signature: str, length: int = 8) -> str:
    """
    Compute short hash for quick comparison.

    Args:
        name: Function/method name
        signature: Function signature
        length: Hash length (default: 8)

    Returns:
        Short hex hash string
    """
    content = f"{name}:{signature}"
    return hashlib.md5(content.encode()).hexdigest()[:length]


# ============================================================================
# Text Processing
# ============================================================================


def truncate_docstring(docstring: Optional[str], max_length: int = 60) -> str:
    """
    Truncate docstring to first sentence or max_length.

    Args:
        docstring: Full docstring text
        max_length: Maximum length (default: 60)

    Returns:
        Truncated docstring
    """
    if not docstring:
        return ""

    # Get first line
    first_line = docstring.split("\n")[0].strip()

    # Remove docstring markers
    first_line = first_line.strip('"""').strip("'''").strip()

    # Find first sentence end
    for end in [". ", ".\n", ".\t"]:
        idx = first_line.find(end)
        if 0 < idx < max_length:
            first_line = first_line[: idx + 1].strip()
            break

    # Truncate if still too long
    if len(first_line) > max_length:
        first_line = first_line[: max_length - 3].rstrip() + "..."

    # Escape quotes
    first_line = first_line.replace('"', "'")

    return first_line


def escape_for_yaml(text: str) -> str:
    """
    Escape text for safe YAML inclusion.

    Args:
        text: Raw text string

    Returns:
        YAML-safe text string
    """
    if not text:
        return ""

    text = text.replace("\n", " ").replace("\r", "").replace("\t", " ")
    text = re.sub(r"\s+", " ", text)  # Collapse whitespace

    # Quote if contains special chars
    if any(c in text for c in ":#[]{}|>"):
        text = f'"{text.replace(chr(34), chr(39))}"'

    return text.strip()


def clean_identifier(name: str) -> str:
    """
    Clean identifier by removing whitespace and special characters.

    Args:
        name: Raw identifier string

    Returns:
        Cleaned identifier
    """
    if not name:
        return ""
    return name.replace("\n", "").replace("\r", "").replace("\t", "").strip()
