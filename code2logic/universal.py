"""
Universal Code Logic Representation (UCLR).

Language-agnostic format for storing code logic that can be
reproduced to any target language with high fidelity.

Features:
- Language-independent representation
- Multi-file project support
- Automatic LLM capability detection
- Chunking for large codebases
- Compression optimization

Usage:
    from code2logic.universal import UniversalReproducer, CodeLogic

    reproducer = UniversalReproducer()
    result = reproducer.reproduce("path/to/file.py", target_lang="python")
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Union

MAX_3 = 3
CONSTANT_5 = 5
CONSTANT_12 = 12
CONSTANT_60 = 60
CONSTANT_200 = 200
MAX_8000 = 8000


MAX_3 = MAX_3
CONSTANT_5 = CONSTANT_5
CONSTANT_12 = CONSTANT_12
CONSTANT_60 = CONSTANT_60
CONSTANT_200 = CONSTANT_200
MAX_8000 = MAX_8000


MAX_3 = MAX_3
CONSTANT_5 = CONSTANT_5
CONSTANT_12 = CONSTANT_12
CONSTANT_60 = CONSTANT_60
CONSTANT_200 = CONSTANT_200
MAX_8000 = MAX_8000


MAX_3 = MAX_3
CONSTANT_5 = CONSTANT_5
CONSTANT_12 = CONSTANT_12
CONSTANT_60 = CONSTANT_60
CONSTANT_200 = CONSTANT_200
MAX_8000 = MAX_8000


# Load .env
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .llm_clients import BaseLLMClient, get_client
from .reproduction import compare_code, extract_code_block


class ElementType(Enum):
    """Types of code elements."""

    IMPORT = "import"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"
    MODULE = "module"


class Language(Enum):
    """Supported languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CSHARP = "csharp"
    SQL = "sql"
    UNKNOWN = "unknown"


@dataclass
class Parameter:
    """Function/method parameter."""

    name: str
    type: str = ""
    default: str = ""
    is_optional: bool = False


@dataclass
class CodeElement:
    """Universal representation of a code element."""

    type: ElementType
    name: str
    docstring: str = ""
    signature: str = ""
    parameters: List[Parameter] = field(default_factory=list)
    return_type: str = ""
    body_hash: str = ""  # Hash of body for change detection
    attributes: List[Dict[str, str]] = field(default_factory=list)
    children: List["CodeElement"] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)  # public, private, async, etc.
    extends: List[str] = field(default_factory=list)
    implements: List[str] = field(default_factory=list)


@dataclass
class CodeLogic:
    """Universal code logic representation for a single file."""

    source_file: str
    source_language: Language
    source_hash: str
    elements: List[CodeElement] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    module_doc: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_file": self.source_file,
            "source_language": self.source_language.value,
            "source_hash": self.source_hash,
            "module_doc": self.module_doc,
            "imports": self.imports,
            "elements": [self._element_to_dict(e) for e in self.elements],
            "metadata": self.metadata,
        }

    def _element_to_dict(self, elem: CodeElement) -> Dict[str, Any]:
        """Convert element to dictionary."""
        return {
            "type": elem.type.value,
            "name": elem.name,
            "docstring": elem.docstring,
            "signature": elem.signature,
            "parameters": [asdict(p) for p in elem.parameters],
            "return_type": elem.return_type,
            "attributes": elem.attributes,
            "children": [self._element_to_dict(c) for c in elem.children],
            "decorators": elem.decorators,
            "modifiers": elem.modifiers,
            "extends": elem.extends,
            "implements": elem.implements,
        }

    def to_compact(self) -> str:
        """Convert to compact string representation."""
        lines = []

        # Header
        lines.append(f"# UCLR: {self.source_file}")
        lines.append(f"# Lang: {self.source_language.value}")
        if self.module_doc:
            lines.append(f"# Doc: {self.module_doc[:100]}")
        lines.append("")

        # Imports
        if self.imports:
            lines.append("@imports")
            for imp in self.imports:
                lines.append(f"  {imp}")
            lines.append("")

        # Elements
        for elem in self.elements:
            lines.extend(self._element_to_compact(elem, 0))

        return "\n".join(lines)

    def _element_to_compact(self, elem: CodeElement, indent: int) -> List[str]:
        """Convert element to compact lines."""
        prefix = "  " * indent
        lines = []

        # Type marker
        type_markers = {
            ElementType.CLASS: "@class",
            ElementType.INTERFACE: "@interface",
            ElementType.STRUCT: "@struct",
            ElementType.FUNCTION: "@func",
            ElementType.METHOD: "@method",
            ElementType.ENUM: "@enum",
            ElementType.TYPE_ALIAS: "@type",
        }
        marker = type_markers.get(elem.type, f"@{elem.type.value}")

        # Decorators
        for dec in elem.decorators:
            lines.append(f"{prefix}{dec}")

        # Modifiers
        mods = " ".join(elem.modifiers) if elem.modifiers else ""

        # Main definition
        if elem.type in [ElementType.CLASS, ElementType.INTERFACE, ElementType.STRUCT]:
            extends = f" extends {', '.join(elem.extends)}" if elem.extends else ""
            implements = (
                f" implements {', '.join(elem.implements)}" if elem.implements else ""
            )
            lines.append(
                f"{prefix}{marker} {mods} {elem.name}{extends}{implements}".strip()
            )

            if elem.docstring:
                lines.append(f"{prefix}  # {elem.docstring[:CONSTANT_60]}")

            # Attributes
            for attr in elem.attributes:
                attr_line = f"{prefix}  .{attr['name']}: {attr.get('type', 'any')}"
                if attr.get("default"):
                    attr_line += f" = {attr['default']}"
                lines.append(attr_line)

            # Children (methods)
            for child in elem.children:
                lines.extend(self._element_to_compact(child, indent + 1))

        elif elem.type in [ElementType.FUNCTION, ElementType.METHOD]:
            params = ", ".join(
                [
                    f"{p.name}: {p.type}" + (f" = {p.default}" if p.default else "")
                    for p in elem.parameters
                ]
            )
            ret = f" -> {elem.return_type}" if elem.return_type else ""
            lines.append(f"{prefix}{marker} {mods} {elem.name}({params}){ret}".strip())

            if elem.docstring:
                lines.append(f"{prefix}  # {elem.docstring[:CONSTANT_60]}")

        elif elem.type == ElementType.ENUM:
            lines.append(f"{prefix}{marker} {elem.name}")
            for attr in elem.attributes:
                lines.append(f"{prefix}  .{attr['name']} = {attr.get('value', '')}")

        lines.append("")
        return lines


class UniversalParser:
    """Parse source code into universal CodeLogic format."""

    # Language detection patterns
    LANG_PATTERNS = {
        Language.PYTHON: [
            r"def \w+\(",
            r"class \w+:",
            r"import \w+",
            r"from \w+ import",
        ],
        Language.JAVASCRIPT: [
            r"function \w+\(",
            r"const \w+ =",
            r"let \w+ =",
            r"module\.exports",
        ],
        Language.TYPESCRIPT: [
            r"interface \w+",
            r": \w+\[\]",
            r"export \{",
            r"type \w+ =",
        ],
        Language.GO: [r"func \w+\(", r"type \w+ struct", r"package \w+"],
        Language.RUST: [r"fn \w+\(", r"struct \w+", r"impl \w+", r"pub fn"],
        Language.JAVA: [r"public class", r"private \w+", r"void \w+\("],
        Language.SQL: [r"CREATE TABLE", r"SELECT .* FROM", r"INSERT INTO"],
    }

    def detect_language(self, content: str, file_ext: str) -> Language:
        """Detect programming language from content and extension."""
        ext_map = {
            ".py": Language.PYTHON,
            ".js": Language.JAVASCRIPT,
            ".ts": Language.TYPESCRIPT,
            ".tsx": Language.TYPESCRIPT,
            ".go": Language.GO,
            ".rs": Language.RUST,
            ".java": Language.JAVA,
            ".sql": Language.SQL,
            ".cs": Language.CSHARP,
        }

        if file_ext in ext_map:
            return ext_map[file_ext]

        # Pattern-based detection
        for lang, patterns in self.LANG_PATTERNS.items():
            matches = sum(1 for p in patterns if re.search(p, content))
            if matches >= 2:
                return lang

        return Language.UNKNOWN

    def parse(self, file_path: Union[str, Path]) -> CodeLogic:
        """Parse source file into CodeLogic."""
        path = Path(file_path)
        content = path.read_text()

        language = self.detect_language(content, path.suffix)
        source_hash = hashlib.md5(content.encode()).hexdigest()[:CONSTANT_12]

        # Parse based on language
        if language == Language.PYTHON:
            return self._parse_python(path, content, source_hash)
        elif language in [Language.JAVASCRIPT, Language.TYPESCRIPT]:
            return self._parse_js_ts(path, content, source_hash, language)
        elif language == Language.GO:
            return self._parse_go(path, content, source_hash)
        elif language == Language.SQL:
            return self._parse_sql(path, content, source_hash)
        elif language == Language.RUST:
            return self._parse_rust(path, content, source_hash)
        elif language == Language.JAVA:
            return self._parse_java(path, content, source_hash)
        elif language == Language.CSHARP:
            return self._parse_csharp(path, content, source_hash)
        else:
            return self._parse_generic(path, content, source_hash, language)

    def _parse_rust(self, path: Path, content: str, hash_: str) -> CodeLogic:
        """Parse Rust file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=Language.RUST,
            source_hash=hash_,
        )

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("use ") and stripped.endswith(";"):
                logic.imports.append(stripped)

        for m in re.finditer(r"^(?:pub\s+)?struct\s+(\w+)", content, re.MULTILINE):
            logic.elements.append(CodeElement(type=ElementType.STRUCT, name=m.group(1)))

        for m in re.finditer(r"^(?:pub\s+)?enum\s+(\w+)", content, re.MULTILINE):
            logic.elements.append(CodeElement(type=ElementType.ENUM, name=m.group(1)))

        for m in re.finditer(r"^(?:pub\s+)?trait\s+(\w+)", content, re.MULTILINE):
            logic.elements.append(
                CodeElement(type=ElementType.INTERFACE, name=m.group(1))
            )

        for m in re.finditer(
            r"^(?:pub\s+)?fn\s+(\w+)\s*\(([^)]*)\)", content, re.MULTILINE
        ):
            logic.elements.append(
                CodeElement(type=ElementType.FUNCTION, name=m.group(1))
            )

        return logic

    def _parse_java(self, path: Path, content: str, hash_: str) -> CodeLogic:
        """Parse Java file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=Language.JAVA,
            source_hash=hash_,
        )

        for m in re.finditer(r"^import\s+([^;]+);", content, re.MULTILINE):
            logic.imports.append(f"import {m.group(1).strip()};")

        for m in re.finditer(
            r"^(?:public\s+)?(?:abstract\s+)?class\s+(\w+)", content, re.MULTILINE
        ):
            logic.elements.append(CodeElement(type=ElementType.CLASS, name=m.group(1)))

        for m in re.finditer(
            r"^(?:public\s+)?interface\s+(\w+)", content, re.MULTILINE
        ):
            logic.elements.append(
                CodeElement(type=ElementType.INTERFACE, name=m.group(1))
            )

        for m in re.finditer(r"^(?:public\s+)?enum\s+(\w+)", content, re.MULTILINE):
            logic.elements.append(CodeElement(type=ElementType.ENUM, name=m.group(1)))

        return logic

    def _parse_csharp(self, path: Path, content: str, hash_: str) -> CodeLogic:
        """Parse C# file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=Language.CSHARP,
            source_hash=hash_,
        )

        for m in re.finditer(r"^using\s+([^;]+);", content, re.MULTILINE):
            logic.imports.append(f"using {m.group(1).strip()};")

        for m in re.finditer(
            r"^(?:public\s+)?interface\s+(I\w+)", content, re.MULTILINE
        ):
            logic.elements.append(
                CodeElement(type=ElementType.INTERFACE, name=m.group(1))
            )

        for m in re.finditer(
            r"^(?:public\s+)?(?:abstract\s+)?class\s+(\w+)", content, re.MULTILINE
        ):
            logic.elements.append(CodeElement(type=ElementType.CLASS, name=m.group(1)))

        for m in re.finditer(r"^(?:public\s+)?record\s+(\w+)", content, re.MULTILINE):
            logic.elements.append(CodeElement(type=ElementType.CLASS, name=m.group(1)))

        return logic

    def _parse_python(self, path: Path, content: str, hash_: str) -> CodeLogic:
        """Parse Python file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=Language.PYTHON,
            source_hash=hash_,
        )

        lines = content.split("\n")
        current_class = None
        in_docstring = False
        docstring_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Module docstring
            if i < CONSTANT_5 and stripped.startswith('"""') and not logic.module_doc:
                if stripped.count('"""') >= 2:
                    logic.module_doc = stripped.strip('"""').strip()
                else:
                    in_docstring = True
                    docstring_lines = [stripped.lstrip('"""')]
                continue

            if in_docstring:
                if '"""' in stripped:
                    docstring_lines.append(stripped.rstrip('"""'))
                    logic.module_doc = " ".join(docstring_lines)[:CONSTANT_200]
                    in_docstring = False
                else:
                    docstring_lines.append(stripped)
                continue

            # Imports
            if stripped.startswith("import ") or stripped.startswith("from "):
                logic.imports.append(stripped)
                continue

            # Decorators
            if stripped.startswith("@") and not stripped.startswith("@dataclass"):
                continue

            # Class
            if stripped.startswith("class "):
                class_match = re.match(r"class (\w+)(?:\((.*?)\))?:", stripped)
                if class_match:
                    name = class_match.group(1)
                    bases = class_match.group(2) or ""

                    is_dataclass = "@dataclass" in "\n".join(
                        lines[max(0, i - MAX_3) : i]
                    )

                    elem = CodeElement(
                        type=ElementType.CLASS,
                        name=name,
                        extends=[b.strip() for b in bases.split(",") if b.strip()],
                        decorators=["@dataclass"] if is_dataclass else [],
                    )
                    logic.elements.append(elem)
                    current_class = elem

            # Class attributes (for dataclasses)
            if current_class and ":" in stripped and not stripped.startswith("def "):
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if any(x in stripped.lower() for x in ["path to", "the ", "a ", "an "]):
                    continue

                attr_match = re.match(r"(\w+)\s*:\s*([^=]+)(?:\s*=\s*(.+))?", stripped)
                if attr_match:
                    attr_name = attr_match.group(1)
                    attr_type = attr_match.group(2).strip()
                    attr_default = (
                        attr_match.group(MAX_3).strip()
                        if attr_match.group(MAX_3)
                        else ""
                    )

                    if attr_name.isidentifier() and attr_name not in [
                        "return",
                        "if",
                        "for",
                    ]:
                        current_class.attributes.append(
                            {
                                "name": attr_name,
                                "type": attr_type,
                                "default": attr_default,
                            }
                        )

            # Function/Method
            if stripped.startswith("def "):
                func_match = re.match(
                    r"def (\w+)\((.*?)\)(?:\s*->\s*(.+?))?:", stripped
                )
                if func_match:
                    name = func_match.group(1)
                    params_str = func_match.group(2)
                    return_type = func_match.group(MAX_3) or ""

                    # Parse parameters
                    params = []
                    if params_str:
                        for param in params_str.split(","):
                            param = param.strip()
                            if not param or param == "self":
                                continue

                            param_match = re.match(
                                r"(\w+)(?:\s*:\s*([^=]+))?(?:\s*=\s*(.+))?", param
                            )
                            if param_match:
                                params.append(
                                    Parameter(
                                        name=param_match.group(1),
                                        type=param_match.group(2).strip()
                                        if param_match.group(2)
                                        else "",
                                        default=param_match.group(MAX_3).strip()
                                        if param_match.group(MAX_3)
                                        else "",
                                    )
                                )

                    elem = CodeElement(
                        type=ElementType.METHOD
                        if current_class
                        else ElementType.FUNCTION,
                        name=name,
                        parameters=params,
                        return_type=return_type.strip() if return_type else "",
                    )

                    if current_class:
                        current_class.children.append(elem)
                    else:
                        logic.elements.append(elem)

            # End of class (rough heuristic)
            if (
                current_class
                and line
                and not line[0].isspace()
                and not stripped.startswith("@")
            ):
                if not stripped.startswith("class ") and not stripped.startswith(
                    "def "
                ):
                    current_class = None

        return logic

    def _parse_js_ts(
        self, path: Path, content: str, hash_: str, lang: Language
    ) -> CodeLogic:
        """Parse JavaScript/TypeScript file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=lang,
            source_hash=hash_,
        )

        lines = content.split("\n")
        current_interface = None
        current_class = None
        brace_depth = 0

        for _i, line in enumerate(lines):
            stripped = line.strip()

            # Track braces
            brace_depth += stripped.count("{") - stripped.count("}")

            # Imports
            if stripped.startswith("import ") or (
                stripped.startswith("const ") and "require" in stripped
            ):
                logic.imports.append(stripped)
                continue

            # Type alias
            if stripped.startswith("type ") and "=" in stripped:
                match = re.match(r"type (\w+)", stripped)
                if match:
                    logic.elements.append(
                        CodeElement(
                            type=ElementType.TYPE_ALIAS,
                            name=match.group(1),
                        )
                    )
                continue

            # Interface (TypeScript)
            if stripped.startswith("interface "):
                match = re.match(r"interface (\w+)(?:\s+extends\s+(\w+))?", stripped)
                if match:
                    elem = CodeElement(
                        type=ElementType.INTERFACE,
                        name=match.group(1),
                        extends=[match.group(2)] if match.group(2) else [],
                    )
                    logic.elements.append(elem)
                    current_interface = elem
                    current_class = None
                continue

            # Interface properties
            if current_interface and ":" in stripped and not stripped.startswith("//"):
                prop_match = re.match(r"(\w+)(?:\?)?:\s*(.+?);?$", stripped)
                if prop_match:
                    current_interface.attributes.append(
                        {
                            "name": prop_match.group(1),
                            "type": prop_match.group(2).rstrip(";"),
                            "optional": "?" in stripped[: stripped.find(":")],
                        }
                    )

            # End interface
            if current_interface and stripped == "}":
                current_interface = None

            # Class
            if "class " in stripped and not stripped.startswith("//"):
                match = re.match(
                    r"(?:export\s+)?class (\w+)(?:<[^>]+>)?(?:\s+extends\s+(\w+))?(?:\s+implements\s+(\w+))?",
                    stripped,
                )
                if match:
                    elem = CodeElement(
                        type=ElementType.CLASS,
                        name=match.group(1),
                        extends=[match.group(2)] if match.group(2) else [],
                        implements=[match.group(MAX_3)] if match.group(MAX_3) else [],
                    )
                    logic.elements.append(elem)
                    current_class = elem
                    current_interface = None
                continue

            # Class properties and methods
            if current_class and not stripped.startswith("//"):
                # Property
                prop_match = re.match(
                    r"(?:private\s+|public\s+|readonly\s+)?(\w+)(?:\?)?:\s*(.+?);?$",
                    stripped,
                )
                if prop_match and "(" not in stripped:
                    current_class.attributes.append(
                        {
                            "name": prop_match.group(1),
                            "type": prop_match.group(2).rstrip(";"),
                        }
                    )

                # Method
                method_match = re.match(
                    r"(?:async\s+)?(?:private\s+|public\s+)?(\w+)\s*\(([^)]*)\)(?:\s*:\s*(.+?))?(?:\s*\{)?",
                    stripped,
                )
                if method_match and stripped.count("(") > 0:
                    name = method_match.group(1)
                    if name not in ["if", "for", "while", "switch"]:
                        params_str = method_match.group(2)
                        return_type = method_match.group(MAX_3) or ""

                        params = []
                        if params_str:
                            for param in params_str.split(","):
                                param = param.strip()
                                if not param:
                                    continue
                                pm = re.match(r"(\w+)(?:\?)?(?:\s*:\s*(.+))?", param)
                                if pm:
                                    params.append(
                                        Parameter(
                                            name=pm.group(1),
                                            type=pm.group(2) or "",
                                        )
                                    )

                        current_class.children.append(
                            CodeElement(
                                type=ElementType.METHOD,
                                name=name,
                                parameters=params,
                                return_type=return_type.rstrip(" {"),
                            )
                        )

            # Standalone function
            func_match = re.match(
                r"(?:export\s+)?(?:async\s+)?function\s+(\w+)(?:<[^>]+>)?\s*\(([^)]*)\)(?:\s*:\s*(.+?))?",
                stripped,
            )
            if func_match:
                name = func_match.group(1)
                params_str = func_match.group(2)
                return_type = func_match.group(MAX_3) or ""

                params = []
                if params_str:
                    for param in params_str.split(","):
                        param = param.strip()
                        if not param:
                            continue
                        pm = re.match(r"(\w+)(?:\?)?(?:\s*:\s*(.+))?", param)
                        if pm:
                            params.append(
                                Parameter(
                                    name=pm.group(1),
                                    type=pm.group(2) or "",
                                )
                            )

                logic.elements.append(
                    CodeElement(
                        type=ElementType.FUNCTION,
                        name=name,
                        parameters=params,
                        return_type=return_type.rstrip(" {"),
                    )
                )

            # Arrow function
            arrow_match = re.match(
                r"(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)(?:\s*:\s*(.+?))?\s*=>",
                stripped,
            )
            if arrow_match:
                name = arrow_match.group(1)
                params_str = arrow_match.group(2)
                return_type = arrow_match.group(MAX_3) or ""

                params = []
                if params_str:
                    for param in params_str.split(","):
                        param = param.strip()
                        if not param:
                            continue
                        pm = re.match(r"(\w+)(?:\?)?(?:\s*:\s*(.+))?", param)
                        if pm:
                            params.append(
                                Parameter(
                                    name=pm.group(1),
                                    type=pm.group(2) or "",
                                )
                            )

                logic.elements.append(
                    CodeElement(
                        type=ElementType.FUNCTION,
                        name=name,
                        parameters=params,
                        return_type=return_type,
                    )
                )

        return logic

    def _parse_go(self, path: Path, content: str, hash_: str) -> CodeLogic:
        """Parse Go file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=Language.GO,
            source_hash=hash_,
        )

        lines = content.split("\n")

        for line in lines:
            stripped = line.strip()

            # Package
            if stripped.startswith("package "):
                logic.metadata["package"] = stripped.split()[1]

            # Imports
            if stripped.startswith("import "):
                logic.imports.append(stripped)

            # Struct
            if "type " in stripped and " struct" in stripped:
                match = re.match(r"type (\w+) struct", stripped)
                if match:
                    logic.elements.append(
                        CodeElement(
                            type=ElementType.STRUCT,
                            name=match.group(1),
                        )
                    )

            # Interface
            if "type " in stripped and " interface" in stripped:
                match = re.match(r"type (\w+) interface", stripped)
                if match:
                    logic.elements.append(
                        CodeElement(
                            type=ElementType.INTERFACE,
                            name=match.group(1),
                        )
                    )

            # Function
            if stripped.startswith("func "):
                match = re.match(r"func (?:\(\w+ \*?(\w+)\) )?(\w+)\((.*?)\)", stripped)
                if match:
                    receiver = match.group(1)
                    name = match.group(2)

                    elem = CodeElement(
                        type=ElementType.METHOD if receiver else ElementType.FUNCTION,
                        name=name,
                    )

                    if receiver:
                        # Find struct and add method
                        for e in logic.elements:
                            if e.name == receiver and e.type == ElementType.STRUCT:
                                e.children.append(elem)
                                break
                    else:
                        logic.elements.append(elem)

        return logic

    def _parse_sql(self, path: Path, content: str, hash_: str) -> CodeLogic:
        """Parse SQL file."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=Language.SQL,
            source_hash=hash_,
        )

        # Tables
        for match in re.finditer(
            r"CREATE TABLE (\w+)\s*\((.*?)\);", content, re.DOTALL | re.IGNORECASE
        ):
            table_name = match.group(1)
            columns_str = match.group(2)

            elem = CodeElement(
                type=ElementType.CLASS,  # Table as class
                name=table_name,
            )

            # Parse columns
            for col_match in re.finditer(r"(\w+)\s+(\w+(?:\([^)]+\))?)", columns_str):
                elem.attributes.append(
                    {
                        "name": col_match.group(1),
                        "type": col_match.group(2),
                    }
                )

            logic.elements.append(elem)

        # Views
        for match in re.finditer(
            r"CREATE (?:OR REPLACE )?VIEW (\w+)", content, re.IGNORECASE
        ):
            logic.elements.append(
                CodeElement(
                    type=ElementType.CLASS,
                    name=match.group(1),
                    modifiers=["view"],
                )
            )

        # Functions
        for match in re.finditer(
            r"CREATE (?:OR REPLACE )?FUNCTION (\w+)", content, re.IGNORECASE
        ):
            logic.elements.append(
                CodeElement(
                    type=ElementType.FUNCTION,
                    name=match.group(1),
                )
            )

        return logic

    def _parse_generic(
        self, path: Path, content: str, hash_: str, lang: Language
    ) -> CodeLogic:
        """Generic parser for unknown languages."""
        logic = CodeLogic(
            source_file=str(path),
            source_language=lang,
            source_hash=hash_,
        )

        # Try to find class-like and function-like patterns
        for match in re.finditer(r"class\s+(\w+)", content, re.IGNORECASE):
            logic.elements.append(
                CodeElement(
                    type=ElementType.CLASS,
                    name=match.group(1),
                )
            )

        for match in re.finditer(
            r"(?:function|def|func|fn)\s+(\w+)", content, re.IGNORECASE
        ):
            logic.elements.append(
                CodeElement(
                    type=ElementType.FUNCTION,
                    name=match.group(1),
                )
            )

        return logic


class CodeGenerator:
    """Generate code from CodeLogic in target language."""

    def generate(self, logic: CodeLogic, target_lang: Language) -> str:
        """Generate code in target language."""
        if target_lang == Language.PYTHON:
            return self._generate_python(logic)
        elif target_lang == Language.TYPESCRIPT:
            return self._generate_typescript(logic)
        elif target_lang == Language.GO:
            return self._generate_go(logic)
        elif target_lang == Language.SQL:
            return self._generate_sql(logic)
        elif target_lang == Language.RUST:
            return self._generate_rust(logic)
        elif target_lang == Language.JAVA:
            return self._generate_java(logic)
        elif target_lang == Language.CSHARP:
            return self._generate_csharp(logic)
        else:
            return self._generate_generic(logic, target_lang)

    def _generate_python(self, logic: CodeLogic) -> str:
        """Generate Python code."""
        lines = []

        # Docstring
        if logic.module_doc:
            lines.append(f'"""{logic.module_doc}"""')
            lines.append("")

        # Imports
        if logic.imports:
            for imp in logic.imports:
                lines.append(imp)
            lines.append("")

        # Check if dataclasses needed
        has_dataclass = any(
            "@dataclass" in e.decorators
            for e in logic.elements
            if e.type == ElementType.CLASS
        )
        if has_dataclass and "from dataclasses import" not in "\n".join(logic.imports):
            lines.insert(0, "from dataclasses import dataclass, field")
            lines.insert(1, "from typing import Optional, List, Dict, Any")
            lines.insert(2, "")

        # Elements
        for elem in logic.elements:
            lines.extend(self._generate_python_element(elem))
            lines.append("")

        return "\n".join(lines)

    def _generate_python_element(self, elem: CodeElement, indent: int = 0) -> List[str]:
        """Generate Python code for element."""
        prefix = "    " * indent
        lines = []

        if elem.type == ElementType.CLASS:
            # Decorators
            for dec in elem.decorators:
                lines.append(f"{prefix}{dec}")

            # Class definition
            bases = ", ".join(elem.extends) if elem.extends else ""
            lines.append(
                f"{prefix}class {elem.name}({bases}):"
                if bases
                else f"{prefix}class {elem.name}:"
            )

            # Docstring
            if elem.docstring:
                lines.append(f'{prefix}    """{elem.docstring}"""')

            # Attributes (for dataclasses)
            if "@dataclass" in elem.decorators:
                for attr in elem.attributes:
                    type_ = attr.get("type", "Any")
                    default = attr.get("default", "")
                    if default:
                        lines.append(f"{prefix}    {attr['name']}: {type_} = {default}")
                    else:
                        lines.append(f"{prefix}    {attr['name']}: {type_}")

            # Methods
            if not elem.children and not elem.attributes:
                lines.append(f"{prefix}    pass")
            else:
                for child in elem.children:
                    lines.extend(self._generate_python_element(child, indent + 1))

        elif elem.type in [ElementType.FUNCTION, ElementType.METHOD]:
            # Parameters
            params = ["self"] if elem.type == ElementType.METHOD else []
            for p in elem.parameters:
                param_str = p.name
                if p.type:
                    param_str += f": {p.type}"
                if p.default:
                    param_str += f" = {p.default}"
                params.append(param_str)

            params_str = ", ".join(params)
            ret = f" -> {elem.return_type}" if elem.return_type else ""

            lines.append(f"{prefix}def {elem.name}({params_str}){ret}:")

            if elem.docstring:
                lines.append(f'{prefix}    """{elem.docstring}"""')

            lines.append(f"{prefix}    pass")

        return lines

    def _generate_typescript(self, logic: CodeLogic) -> str:
        """Generate TypeScript code."""
        lines = []

        for elem in logic.elements:
            if elem.type == ElementType.INTERFACE:
                lines.append(f"interface {elem.name} {{")
                for attr in elem.attributes:
                    lines.append(f"    {attr['name']}: {attr.get('type', 'any')};")
                lines.append("}")
                lines.append("")

            elif elem.type == ElementType.CLASS:
                extends = f" extends {', '.join(elem.extends)}" if elem.extends else ""
                lines.append(f"class {elem.name}{extends} {{")

                for attr in elem.attributes:
                    lines.append(f"    {attr['name']}: {attr.get('type', 'any')};")

                for child in elem.children:
                    params = ", ".join(
                        [f"{p.name}: {p.type or 'any'}" for p in child.parameters]
                    )
                    ret = f": {child.return_type}" if child.return_type else ""
                    lines.append(f"    {child.name}({params}){ret} {{ }}")

                lines.append("}")
                lines.append("")

            elif elem.type == ElementType.FUNCTION:
                params = ", ".join(
                    [f"{p.name}: {p.type or 'any'}" for p in elem.parameters]
                )
                ret = f": {elem.return_type}" if elem.return_type else ""
                lines.append(f"function {elem.name}({params}){ret} {{ }}")
                lines.append("")

        return "\n".join(lines)

    def _generate_go(self, logic: CodeLogic) -> str:
        """Generate Go code."""
        lines = []

        if logic.metadata.get("package"):
            lines.append(f"package {logic.metadata['package']}")
            lines.append("")

        for elem in logic.elements:
            if elem.type == ElementType.STRUCT:
                lines.append(f"type {elem.name} struct {{")
                for attr in elem.attributes:
                    lines.append(
                        f"    {attr['name']} {attr.get('type', 'interface{}')}"
                    )
                lines.append("}")
                lines.append("")

            elif elem.type == ElementType.FUNCTION:
                lines.append(f"func {elem.name}() {{")
                lines.append("}")
                lines.append("")

        return "\n".join(lines)

    def _generate_sql(self, logic: CodeLogic) -> str:
        """Generate SQL code."""
        lines = []

        for elem in logic.elements:
            if elem.type == ElementType.CLASS and "view" not in elem.modifiers:
                lines.append(f"CREATE TABLE {elem.name} (")
                cols = []
                for attr in elem.attributes:
                    cols.append(f"    {attr['name']} {attr.get('type', 'TEXT')}")
                lines.append(",\n".join(cols))
                lines.append(";")
                lines.append("")

        return "\n".join(lines)

    def _generate_rust(self, logic: CodeLogic) -> str:
        """Generate Rust code."""
        lines: List[str] = []

        for imp in logic.imports:
            if (imp or "").strip():
                lines.append(imp)
        if lines:
            lines.append("")

        for elem in logic.elements:
            if elem.type == ElementType.STRUCT:
                lines.append(f"pub struct {elem.name} {{")
                lines.append("}")
                lines.append("")
            elif elem.type == ElementType.ENUM:
                lines.append(f"pub enum {elem.name} {{")
                lines.append("}")
                lines.append("")
            elif elem.type in (ElementType.FUNCTION, ElementType.METHOD):
                lines.append(f"pub fn {elem.name}() {{")
                lines.append("}")
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _generate_java(self, logic: CodeLogic) -> str:
        """Generate Java code."""
        lines: List[str] = []

        for imp in logic.imports:
            if (imp or "").strip():
                lines.append(imp)
        if lines:
            lines.append("")

        main_class = None
        for elem in logic.elements:
            if elem.type == ElementType.CLASS:
                main_class = elem.name
                break
        if not main_class:
            main_class = "Generated"

        lines.append(f"public class {main_class} {{")
        for elem in logic.elements:
            if elem.type == ElementType.FUNCTION:
                lines.append(f"    public static void {elem.name}() {{ }}")
        lines.append("}")

        return "\n".join(lines).rstrip() + "\n"

    def _generate_csharp(self, logic: CodeLogic) -> str:
        """Generate C# code."""
        lines: List[str] = []

        for imp in logic.imports:
            if (imp or "").strip():
                lines.append(imp)
        if lines:
            lines.append("")

        main_class = None
        for elem in logic.elements:
            if elem.type == ElementType.CLASS:
                main_class = elem.name
                break
        if not main_class:
            main_class = "Generated"

        lines.append(f"public class {main_class} {{")
        for elem in logic.elements:
            if elem.type == ElementType.FUNCTION:
                lines.append(f"    public static void {elem.name}() {{ }}")
        lines.append("}")

        return "\n".join(lines).rstrip() + "\n"

    def _generate_generic(self, logic: CodeLogic, target: Language) -> str:
        """Generate generic code."""
        return logic.to_compact()


class UniversalReproducer:
    """Universal code reproduction system."""

    def __init__(self, client: BaseLLMClient = None):
        """Initialize reproducer."""
        self.client = client
        self.parser = UniversalParser()
        self.generator = CodeGenerator()

    def _get_client(self) -> BaseLLMClient:
        """Get or create LLM client."""
        if self.client is None:
            self.client = get_client()
        return self.client

    def extract_logic(self, file_path: str) -> CodeLogic:
        """Extract code logic from file."""
        return self.parser.parse(file_path)

    def reproduce(
        self,
        source_path: str,
        target_lang: str = None,
        output_dir: str = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """Reproduce code from source file.

        Args:
            source_path: Source file path
            target_lang: Target language (default: same as source)
            output_dir: Output directory
            use_llm: Whether to use LLM for generation

        Returns:
            Reproduction results
        """
        path = Path(source_path)
        original = path.read_text()

        # Extract logic
        logic = self.extract_logic(source_path)

        # Determine target language
        if target_lang:
            target = Language(target_lang.lower())
        else:
            target = logic.source_language

        # Generate code
        if use_llm:
            generated = self._generate_with_llm(logic, target)
        else:
            generated = self.generator.generate(logic, target)

        # Compare (if same language)
        if target == logic.source_language:
            comparison = compare_code(original, generated)
        else:
            comparison = {"similarity_percent": 0, "structural_score": 0}

        # Calculate compression
        logic_size = len(logic.to_compact())
        compression = len(original) / max(logic_size, 1)

        result = {
            "source_file": source_path,
            "source_language": logic.source_language.value,
            "target_language": target.value,
            "source_chars": len(original),
            "logic_chars": logic_size,
            "generated_chars": len(generated),
            "compression_ratio": compression,
            "similarity": comparison.get("similarity_percent", 0),
            "structural_score": comparison.get("structural_score", 0),
            "logic": logic.to_dict(),
        }

        # Save
        if output_dir:
            self._save_result(Path(output_dir), original, logic, generated, result)

        return result

    def _generate_with_llm(self, logic: CodeLogic, target: Language) -> str:
        """Generate code using LLM."""
        client = self._get_client()
        compact = logic.to_compact()

        lang_names = {
            Language.PYTHON: "Python",
            Language.JAVASCRIPT: "JavaScript",
            Language.TYPESCRIPT: "TypeScript",
            Language.GO: "Go",
            Language.SQL: "SQL",
            Language.RUST: "Rust",
            Language.JAVA: "Java",
        }
        target_name = lang_names.get(target, target.value)

        system = f"""You are an expert {target_name} developer. Generate production-ready code.
Rules:
1. Generate ONLY code, no explanations
2. Include all imports
3. Add docstrings/comments
4. Include type hints where applicable
5. Code must be complete and runnable

Output: Return ONLY code in ```{target.value} ... ``` blocks."""

        prompt = f"""Generate {target_name} code from this Universal Code Logic Representation (UCLR):

{compact}

Generate complete, working {target_name} code that implements all elements."""

        response = client.generate(prompt, system=system, max_tokens=MAX_8000)
        return extract_code_block(response, target.value)

    def _save_result(
        self,
        output_dir: Path,
        original: str,
        logic: CodeLogic,
        generated: str,
        result: Dict[str, Any],
    ):
        """Save reproduction results."""
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "original.txt").write_text(original)
        (output_dir / "logic.uclr").write_text(logic.to_compact())
        (output_dir / "logic.json").write_text(json.dumps(logic.to_dict(), indent=2))
        (output_dir / "generated.txt").write_text(generated)

        report = f"""# Universal Reproduction Report

## Source
- **File:** {result["source_file"]}
- **Language:** {result["source_language"]}
- **Target:** {result["target_language"]}

## Metrics
| Metric | Value |
|--------|-------|
| Source chars | {result["source_chars"]} |
| Logic chars | {result["logic_chars"]} |
| Generated chars | {result["generated_chars"]} |
| Compression | {result["compression_ratio"]:.2f}x |
| Similarity | {result["similarity"]:.1f}% |
| Structural | {result["structural_score"]:.1f}% |
"""
        (output_dir / "REPORT.md").write_text(report)


def reproduce_file(
    source_path: str,
    target_lang: str = None,
    output_dir: str = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Convenience function for single file reproduction.

    Args:
        source_path: Source file path
        target_lang: Target language
        output_dir: Output directory
        use_llm: Use LLM for generation

    Returns:
        Reproduction results
    """
    reproducer = UniversalReproducer()
    return reproducer.reproduce(source_path, target_lang, output_dir, use_llm)
