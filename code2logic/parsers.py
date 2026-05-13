"""
Code parsers for multiple languages.

Includes:
- TreeSitterParser: High-accuracy AST parsing using Tree-sitter
- UniversalParser: Fallback regex/AST parser for environments without Tree-sitter
"""

import ast
import re
import textwrap
from typing import List, Optional

from .intent import EnhancedIntentGenerator
from .models import (
    AttributeInfo,
    ClassInfo,
    ConstantInfo,
    FieldInfo,
    FunctionInfo,
    ModuleInfo,
    TypeInfo,
)

CONSTANT_3 = 3
PORT_5 = 5
CONSTANT_8 = 8
CONSTANT_15 = 15
PORT_20 = 20
CONSTANT_25 = 25
CONSTANT_40 = 40
CONSTANT_50 = 50
CONSTANT_80 = 80
CONSTANT_200 = 200
CONSTANT_400 = 400
CONSTANT_500 = 500


CONSTANT_3 = CONSTANT_3
PORT_5 = PORT_5
CONSTANT_8 = CONSTANT_8
CONSTANT_15 = CONSTANT_15
PORT_20 = PORT_20
CONSTANT_25 = CONSTANT_25
CONSTANT_40 = CONSTANT_40
CONSTANT_50 = CONSTANT_50
CONSTANT_80 = CONSTANT_80
CONSTANT_200 = CONSTANT_200
CONSTANT_400 = CONSTANT_400
CONSTANT_500 = CONSTANT_500


CONSTANT_3 = CONSTANT_3
PORT_5 = PORT_5
CONSTANT_8 = CONSTANT_8
CONSTANT_15 = CONSTANT_15
PORT_20 = PORT_20
CONSTANT_25 = CONSTANT_25
CONSTANT_40 = CONSTANT_40
CONSTANT_50 = CONSTANT_50
CONSTANT_80 = CONSTANT_80
CONSTANT_200 = CONSTANT_200
CONSTANT_400 = CONSTANT_400
CONSTANT_500 = CONSTANT_500


CONSTANT_3 = CONSTANT_3
PORT_5 = PORT_5
CONSTANT_8 = CONSTANT_8
CONSTANT_15 = CONSTANT_15
PORT_20 = PORT_20
CONSTANT_25 = CONSTANT_25
CONSTANT_40 = CONSTANT_40
CONSTANT_50 = CONSTANT_50
CONSTANT_80 = CONSTANT_80
CONSTANT_200 = CONSTANT_200
CONSTANT_400 = CONSTANT_400
CONSTANT_500 = CONSTANT_500


# Optional Tree-sitter imports
TREE_SITTER_AVAILABLE = False
try:
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    pass


def _normalize_import_path(import_path: str) -> str:
    """Normalize import path by removing duplicate suffix segments."""
    if not import_path:
        return import_path
    parts = import_path.split(".")
    if len(parts) >= 2 and parts[-1] == parts[-2]:
        parts = parts[:-1]
    return ".".join(parts)


def _clean_imports(imports: List[str]) -> List[str]:
    """Deduplicate and normalize import paths while preserving order."""
    seen = set()
    cleaned = []
    for imp in imports:
        if not imp:
            continue
        norm = _normalize_import_path(imp.strip())
        if norm and norm not in seen:
            seen.add(norm)
            cleaned.append(norm)
    return cleaned


def _combine_import_name(module_name: str, identifier: str) -> str:
    """Combine module and identifier while avoiding duplicate suffixes."""
    if not module_name:
        return identifier
    tail = module_name.split(".")[-1]
    if tail == identifier:
        return module_name
    return f"{module_name}.{identifier}"


def _truncate_constant_value(value_text: str, limit: int = CONSTANT_400) -> str:
    """Return a trimmed single-line snippet for constant values."""
    if not value_text:
        return ""
    snippet = value_text.replace("\n", " ").strip()
    if len(snippet) > limit:
        snippet = snippet[: limit - CONSTANT_3].rstrip() + "..."
    return snippet


def _py_expr_to_dotted_name(expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        base = _py_expr_to_dotted_name(expr.value)
        return f"{base}.{expr.attr}" if base else expr.attr
    if isinstance(expr, ast.Call):
        if isinstance(expr.func, ast.Name) and expr.func.id == "super":
            return "super"
        return _py_expr_to_dotted_name(expr.func)
    if isinstance(expr, ast.Subscript):
        return _py_expr_to_dotted_name(expr.value)
    return ""


class _PyFunctionBodyAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.calls = []
        self.raises = []
        self.complexity = 1
        self._seen_calls = set()
        self._seen_raises = set()

    def _add_call(self, name: str) -> None:
        if not name:
            return
        if name in self._seen_calls:
            return
        if len(self.calls) >= CONSTANT_80:
            return
        self._seen_calls.add(name)
        self.calls.append(name)

    def _add_raise(self, name: str) -> None:
        if not name:
            return
        if name in self._seen_raises:
            return
        if len(self.raises) >= CONSTANT_40:
            return
        self._seen_raises.add(name)
        self.raises.append(name)

    def visit_Call(self, node):
        try:
            name = _py_expr_to_dotted_name(node.func)
        except Exception:
            name = ""
        if name:
            self._add_call(name)
        self.generic_visit(node)

    def visit_Raise(self, node):
        exc_name = ""
        try:
            exc = node.exc
            if isinstance(exc, ast.Call):
                exc_name = _py_expr_to_dotted_name(exc.func)
            elif isinstance(exc, ast.Name):
                exc_name = exc.id
            elif isinstance(exc, ast.Attribute):
                exc_name = _py_expr_to_dotted_name(exc)
        except Exception:
            exc_name = ""

        if exc_name:
            self._add_raise(exc_name)
        self.generic_visit(node)

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_IfExp(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        try:
            if isinstance(node.op, (ast.And, ast.Or)):
                self.complexity += max(0, len(getattr(node, "values", []) or []) - 1)
        except Exception:
            pass
        self.generic_visit(node)

    def visit_Try(self, node):
        try:
            self.complexity += len(getattr(node, "handlers", []) or [])
        except Exception:
            pass
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.complexity += 1
        try:
            self.complexity += len(getattr(node, "ifs", []) or [])
        except Exception:
            pass
        self.generic_visit(node)

    def visit_Match(self, node):
        try:
            self.complexity += len(getattr(node, "cases", []) or [])
        except Exception:
            pass
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        return

    def visit_AsyncFunctionDef(self, node):
        return

    def visit_ClassDef(self, node):
        return

    def visit_Lambda(self, node):
        return


def _analyze_python_function_node(func_node):
    analyzer = _PyFunctionBodyAnalyzer()
    for stmt in getattr(func_node, "body", []) or []:
        analyzer.visit(stmt)
    return analyzer.calls, analyzer.raises, max(1, analyzer.complexity)


class TreeSitterParser:
    """
    Parser using Tree-sitter for high-accuracy AST parsing.

    Supports Python, JavaScript, and TypeScript with 99% accuracy.
    Falls back gracefully if Tree-sitter libraries are not installed.

    Example:
        >>> parser = TreeSitterParser()
        >>> if parser.is_available('python'):
        ...     module = parser.parse('main.py', content, 'python')
    """

    def __init__(self):
        """Initialize Tree-sitter parsers for available languages."""
        self.parsers: dict = {}
        self.languages: dict = {}
        self.intent_gen = EnhancedIntentGenerator()

        if TREE_SITTER_AVAILABLE:
            self._init_parsers()

    def _init_parsers(self):
        """Initialize parsers for each supported language."""
        try:
            # Python
            self.languages["python"] = Language(tspython.language())
            self.parsers["python"] = Parser(self.languages["python"])

            # JavaScript
            self.languages["javascript"] = Language(tsjavascript.language())
            self.parsers["javascript"] = Parser(self.languages["javascript"])

            # TypeScript - try dedicated parser, fall back to JS
            try:
                import tree_sitter_typescript as tstypescript

                self.languages["typescript"] = Language(
                    tstypescript.language_typescript()
                )
                self.parsers["typescript"] = Parser(self.languages["typescript"])
            except ImportError:
                self.languages["typescript"] = self.languages["javascript"]
                self.parsers["typescript"] = self.parsers["javascript"]

        except Exception as e:
            import sys

            print(f"Tree-sitter init warning: {e}", file=sys.stderr)

    def is_available(self, language: str) -> bool:
        """Check if Tree-sitter parser is available for a language."""
        return language in self.parsers

    @classmethod
    def get_supported_languages(cls) -> List[str]:
        """Get list of potentially supported languages."""
        return ["python", "javascript", "typescript"]

    def parse(self, filepath: str, content: str, language: str) -> Optional[ModuleInfo]:
        """
        Parse a source file using Tree-sitter.

        Args:
            filepath: Relative path to the file
            content: File content as string
            language: Programming language

        Returns:
            ModuleInfo if parsing succeeds, None otherwise
        """
        if language not in self.parsers:
            return None

        parser = self.parsers[language]
        tree = parser.parse(bytes(content, "utf8"))

        if language == "python":
            return self._parse_python(filepath, content, tree)
        elif language in ("javascript", "typescript"):
            return self._parse_js_ts(filepath, content, tree, language)

        return None

    def _parse_python(self, filepath: str, content: str, tree) -> ModuleInfo:
        """Parse Python source using Tree-sitter AST."""
        root = tree.root_node
        imports, classes, functions, types, constants, exports = [], [], [], [], [], []
        docstring = None

        # Track conditional imports (try/except)
        conditional_imports = []
        type_checking_imports = []
        aliases = {}

        for child in root.children:
            node_type = child.type

            # Module docstring
            if node_type == "expression_statement" and not docstring:
                expr = child.children[0] if child.children else None
                if expr and expr.type == "string":
                    docstring = self._extract_string(expr, content)

            # Regular imports
            elif node_type == "import_statement":
                imports.extend(self._extract_py_import(child, content))
            elif node_type in (
                "import_from_statement",
                "from_import_statement",
                "import_from",
            ):
                imports.extend(self._extract_py_from_import(child, content))

            # Conditional imports (try/except blocks)
            elif node_type == "try_statement":
                try_imports = self._extract_conditional_imports(child, content)
                if try_imports:
                    conditional_imports.extend(try_imports)
                    # Also add to regular imports but mark as conditional
                    imports.extend(try_imports)

            # Classes
            elif node_type == "class_definition":
                cls = self._extract_py_class(child, content, filepath=filepath)
                if cls:
                    classes.append(cls)
                    if not cls.name.startswith("_"):
                        exports.append(cls.name)

                    enum_type = self._extract_py_enum(child, content)
                    if enum_type:
                        types.append(enum_type)
            # Top-level functions (regular or decorated)
            elif node_type == "function_definition":
                func = self._extract_py_function(child, content, filepath=filepath)
                if func:
                    functions.append(func)
                    if not func.name.startswith("_"):
                        exports.append(func.name)
            elif node_type == "decorated_definition":
                # Handle decorated functions
                inner_func = self._find_child(child, "function_definition")
                if inner_func:
                    func = self._extract_py_function(
                        inner_func, content, child, filepath=filepath
                    )
                    if func:
                        functions.append(func)
                        if not func.name.startswith("_"):
                            exports.append(func.name)

                # Handle decorated classes (e.g., @dataclass)
                inner_class = self._find_child(child, "class_definition")
                if inner_class:
                    cls = self._extract_py_class(
                        inner_class, content, decorated_node=child, filepath=filepath
                    )
                    if cls:
                        classes.append(cls)
                        if not cls.name.startswith("_"):
                            exports.append(cls.name)

                        enum_type = self._extract_py_enum(inner_class, content)
                        if enum_type:
                            types.append(enum_type)

            # Constants with enhanced extraction
            if node_type == "expression_statement":
                const = self._extract_py_constant(child, content)
                if const:
                    constants.append(const)
                    # Add constants to exports if they're uppercase (convention)
                    if const.name.isupper():
                        exports.append(const.name)

        # Deduplicate imports and normalize names at extraction time
        lines = content.split("\n")
        file_bytes = len(content.encode("utf-8", errors="ignore"))

        # Extract TYPE_CHECKING and aliases from the entire tree
        type_checking_imports = self._extract_type_checking_imports(root, content)
        aliases = self._extract_aliases(root, content)

        # Create enhanced constants with conditional imports
        enhanced_constants = constants[:10]
        if conditional_imports:
            enhanced_constants.extend(
                [f"conditional:{imp}" for imp in conditional_imports[:PORT_5]]
            )

        return ModuleInfo(
            path=filepath,
            language="python",
            imports=_clean_imports(imports)[:PORT_20],
            exports=exports,
            classes=classes,
            functions=functions,
            types=types,
            constants=enhanced_constants,
            type_checking_imports=type_checking_imports,
            optional_imports=[],  # TODO: implement proper optional import extraction
            aliases=aliases,
            docstring=self._truncate_docstring(docstring),
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("#")]
            ),
            file_bytes=file_bytes,
        )

    def _extract_constants(self, tree, content: str) -> List[ConstantInfo]:
        """Extract module-level UPPERCASE constants."""
        constants = []
        for node in tree.root_node.children:
            if node.type == "expression_statement":
                expr = node.children[0] if node.children else None
                if expr and expr.type == "assignment":
                    # Get the target
                    left = expr.children[0] if expr.children else None
                    if left and left.type == "identifier":
                        name = self._text(left, content)
                        if name.isupper():  # Convention: CONSTANTS are UPPERCASE
                            const = ConstantInfo(name=name)

                            # Get the value
                            right = expr.children[1] if len(expr.children) > 1 else None
                            if right:
                                value_text = self._text(right, content).strip()
                                const.value = (
                                    value_text
                                    if len(value_text) <= CONSTANT_200
                                    else None
                                )

                                # For dictionaries, extract keys
                                if value_text.startswith("{") and value_text.endswith(
                                    "}"
                                ):
                                    # Simple regex to extract keys
                                    import re

                                    keys = re.findall(
                                        r"'([^']+)'|'([^']+)'",
                                        value_text[:CONSTANT_500],
                                    )
                                    const.value_keys = [
                                        k for pair in keys for k in pair if k
                                    ][:10]

                            constants.append(const)

        return constants[:CONSTANT_15]

    def _extract_type_checking_imports(self, tree, content: str) -> List[str]:
        """Extract TYPE_CHECKING block imports."""
        type_checking_imports = []

        for node in tree.children:  # tree is already the root node
            if node.type == "if_statement":
                # Check if this is `if TYPE_CHECKING:`
                condition = self._find_child(node, "condition")
                if condition:
                    cond_text = self._text(condition, content).strip()
                    if "TYPE_CHECKING" in cond_text:
                        # Extract imports from the body
                        body = self._find_child(node, "body")
                        if body:
                            for child in body.children:
                                if child.type == "import_statement":
                                    type_checking_imports.extend(
                                        self._extract_py_import(child, content)
                                    )
                                elif child.type in (
                                    "import_from_statement",
                                    "from_import_statement",
                                    "import_from",
                                ):
                                    type_checking_imports.extend(
                                        self._extract_py_from_import(child, content)
                                    )
                        break

        return type_checking_imports

    def _extract_conditional_imports(self, node, content: str) -> List[str]:
        """Extract imports from try/except blocks."""
        imports = []

        # Find the try body
        try_body = self._find_child(node, "block")
        if try_body:
            for child in try_body.children:
                if child.type == "import_statement":
                    imports.extend(self._extract_py_import(child, content))
                elif child.type in (
                    "import_from_statement",
                    "from_import_statement",
                    "import_from",
                ):
                    imports.extend(self._extract_py_from_import(child, content))

        return imports

    def _extract_aliases(self, tree, content: str) -> dict:
        """Extract module aliases (import X as Y)."""
        aliases = {}

        for node in tree.children:  # tree is already the root node
            if node.type == "import_statement":
                for c in node.children:
                    if c.type == "aliased_import":
                        orig_name = None
                        alias_name = None

                        # Find the original name and alias
                        for subchild in c.children:
                            if subchild.type == "dotted_name":
                                orig_name = self._text(subchild, content)
                            elif (
                                subchild.type == "identifier"
                                and subchild != c.children[0]
                            ):
                                alias_name = self._text(subchild, content)

                        if orig_name and alias_name:
                            aliases[alias_name] = orig_name

            elif node.type in (
                "import_from_statement",
                "from_import_statement",
                "import_from",
            ):
                for c in node.children:
                    if c.type == "aliased_import":
                        orig_name = None
                        alias_name = None

                        for subchild in c.children:
                            if subchild.type == "identifier" and "as" not in self._text(
                                subchild, content
                            ):
                                orig_name = self._text(subchild, content)
                            elif subchild.type == "identifier" and "as" in self._text(
                                subchild, content
                            ):
                                # This is the alias part
                                pass

                        # Extract from the full text
                        text = self._text(c, content)
                        if " as " in text:
                            parts = text.split(" as ")
                            if len(parts) == 2:
                                orig_name = parts[0].strip()
                                alias_name = parts[1].strip()

                        if orig_name and alias_name:
                            aliases[alias_name] = orig_name

        return aliases

    def _extract_py_function(
        self, node, content: str, decorated_node=None, filepath: Optional[str] = None
    ) -> Optional[FunctionInfo]:
        """Extract Python function from AST node."""
        name_node = self._find_child(node, "identifier")
        if not name_node:
            return None
        name = self._text(name_node, content).strip()

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        if node.end_point[1] == 0 and end_line > start_line:
            end_line -= 1
        line_count = max(1, end_line - start_line + 1)

        calls: List[str] = []
        raises: List[str] = []
        complexity = 1
        is_async = False
        func_node_for_ast = None
        try:
            func_src = textwrap.dedent(self._text(node, content))
            is_async = func_src.lstrip().startswith("async def")
            padded_src = ("\n" * max(0, start_line - 1)) + func_src
            parsed = ast.parse(padded_src, filename=filepath or "<unknown>")
            if parsed.body and isinstance(
                parsed.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                is_async = isinstance(parsed.body[0], ast.AsyncFunctionDef)
                func_node_for_ast = parsed.body[0]
                calls, raises, complexity = _analyze_python_function_node(
                    parsed.body[0]
                )
        except Exception:
            pass

        # Parameters - use AST-parsed function (includes defaults) when possible
        params: List[str] = []
        if func_node_for_ast is not None:
            try:
                params = (
                    UniversalParser()
                    ._extract_ast_function(func_node_for_ast)
                    .params[:CONSTANT_8]
                )
            except Exception:
                params = []

        # If AST parsing failed, fall back to TreeSitter extraction
        if not params:
            params_node = self._find_child(node, "parameters")
            if params_node:
                for p in params_node.children:
                    if p.type == "identifier":
                        params.append(self._text(p, content))
                    elif p.type == "typed_parameter":
                        param_name = None
                        param_type = None
                        for sub in p.children:
                            if sub.type == "identifier":
                                param_name = self._text(sub, content)
                            elif sub.type == "type":
                                param_type = self._text(sub, content)
                        if param_name:
                            if param_type:
                                params.append(f"{param_name}:{param_type}")
                            else:
                                params.append(param_name)

        # Decorators
        decorators = []
        if decorated_node:
            for c in decorated_node.children:
                if c.type == "decorator":
                    dec_text = self._text(c, content).lstrip("@")
                    decorators.append(dec_text.split("(")[0])

        # Return type
        return_type = None
        return_ann = self._find_child(node, "type")
        if return_ann:
            return_type = self._text(return_ann, content)

        # Docstring
        docstring = None
        body = self._find_child(node, "block")
        if body and body.children:
            first_child = body.children[0]
            if first_child.type == "expression_statement":
                expr = first_child.children[0] if first_child.children else None
                if expr and expr.type == "string":
                    docstring = self._extract_string(expr, content)

        return FunctionInfo(
            name=name,
            params=params[:CONSTANT_8],
            return_type=return_type,
            docstring=self._truncate_docstring(docstring),
            calls=calls,
            raises=raises,
            complexity=complexity,
            lines=line_count,
            decorators=decorators,
            is_async=is_async,
            is_static="staticmethod" in decorators,
            is_classmethod="classmethod" in decorators,
            is_property="property" in decorators,
            intent=self.intent_gen.generate(name),
            start_line=start_line,
            end_line=end_line,
            is_private=name.startswith("_") and not name.startswith("__"),
        )

    def _extract_py_enum(self, node, content: str) -> Optional[TypeInfo]:
        """Extract Python Enum (values) as TypeInfo(kind='enum')."""
        try:
            name_node = self._find_child(node, "identifier")
            if not name_node:
                return None
            name = self._text(name_node, content).strip()

            arg_list = self._find_child(node, "argument_list")
            bases = []
            if arg_list:
                for c in arg_list.children:
                    if c.type in ("identifier", "attribute"):
                        bases.append(self._text(c, content).strip())
            if not any(
                b.endswith("Enum") or b in ("Enum", "IntEnum", "StrEnum") for b in bases
            ):
                return None

            values: List[str] = []
            body = self._find_child(node, "block")
            if body:
                for child in body.children:
                    if child.type != "expression_statement" or not child.children:
                        continue
                    expr = child.children[0]
                    if expr.type != "assignment":
                        continue
                    left = expr.children[0] if expr.children else None
                    right = expr.children[-1] if len(expr.children) > 1 else None
                    if not left or left.type != "identifier":
                        continue
                    member = self._text(left, content).strip()
                    if not member or member.startswith("_"):
                        continue
                    val_text = self._text(right, content).strip() if right else ""
                    values.append(f"{member}={val_text}" if val_text else member)
                    if len(values) >= CONSTANT_25:
                        break

            return TypeInfo(
                name=name, kind="enum", definition="", values=values or None
            )
        except Exception:
            return None

    def _extract_py_class(
        self, node, content: str, decorated_node=None, filepath: Optional[str] = None
    ) -> Optional[ClassInfo]:
        """Extract Python class from AST node."""
        name_node = self._find_child(node, "identifier")
        if not name_node:
            return None
        name = self._text(name_node, content).strip()

        # Base classes
        bases = []
        arg_list = self._find_child(node, "argument_list")
        if arg_list:
            for c in arg_list.children:
                if c.type in ("identifier", "attribute"):
                    bases.append(self._text(c, content))

        # Check for dataclass decorator
        decorators = []
        is_dataclass = False
        # Use provided decorated_node or try to find parent
        dec_source = decorated_node or getattr(node, "parent", None)
        if dec_source and dec_source.type == "decorated_definition":
            for c in dec_source.children:
                if c.type == "decorator":
                    dec_text = self._text(c, content).lstrip("@")
                    decorators.append(dec_text.split("(")[0])
                    if "dataclass" in dec_text:
                        is_dataclass = True

        # Docstring and methods
        docstring = None
        methods = []
        fields = []
        attributes = []
        properties = []
        body = self._find_child(node, "block")
        if body:
            for i, child in enumerate(body.children):
                if i == 0 and child.type == "expression_statement":
                    expr = child.children[0] if child.children else None
                    if expr and expr.type == "string":
                        docstring = self._extract_string(expr, content)

                if child.type == "function_definition":
                    m = self._extract_py_function(child, content, filepath=filepath)
                    if m:
                        methods.append(m)
                        # Extract self.x = ... from __init__ method
                        if m.name == "__init__" and not is_dataclass:
                            init_attrs = self._extract_init_attributes(child, content)
                            attributes.extend(init_attrs)
                elif child.type == "decorated_definition":
                    inner = self._find_child(child, "function_definition")
                    if inner:
                        m = self._extract_py_function(
                            inner, content, child, filepath=filepath
                        )
                        if m:
                            methods.append(m)

                # Extract dataclass fields (class-level annotated assignments)
                elif is_dataclass and child.type == "expression_statement":
                    field = self._extract_dataclass_field(child, content)
                    if field:
                        fields.append(field)

                # Extract class-level properties (annotated assignments without dataclass)
                elif child.type == "expression_statement" and not is_dataclass:
                    # Check for annotated assignment like "x: int" or "x: int = 5"
                    prop = self._extract_class_property(child, content)
                    if prop:
                        properties.append(prop)

        return ClassInfo(
            name=name,
            bases=bases,
            decorators=decorators,
            docstring=self._truncate_docstring(docstring),
            is_dataclass=is_dataclass,
            fields=fields,
            attributes=attributes,
            properties=properties,
            methods=methods,
            is_interface=False,
            is_abstract="ABC" in bases or "ABCMeta" in bases,
            generic_params=[],
        )

    def _extract_dataclass_field(self, node, content: str) -> Optional[FieldInfo]:
        """Extract dataclass field from assignment."""
        # Fallback: parse annotated assignment text (e.g. "x: int = 1")
        try:
            raw_stmt = self._text(node, content).strip()
        except Exception:
            raw_stmt = ""
        if raw_stmt:
            m = re.match(
                r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<typ>[^=]+?)(?:\s*=\s*(?P<rhs>.+))?$",
                raw_stmt,
            )
            if m:
                name = m.group("name")
                type_annotation = (m.group("typ") or "").strip()
                rhs = (m.group("rhs") or "").strip()

                default = None
                default_factory = None
                if rhs:
                    if rhs.startswith("field(") and "default_factory=" in rhs:
                        factory_match = (
                            rhs.split("default_factory=")[1].split(",")[0].split(")")[0]
                        )
                        default_factory = factory_match.strip()
                    else:
                        default = rhs

                return FieldInfo(
                    name=name,
                    type_annotation=type_annotation,
                    default=default,
                    default_factory=default_factory,
                )

        if node.children:
            expr = node.children[0]
            if expr.type == "assignment":
                left = expr.children[0] if expr.children else None
                if left and left.type == "identifier":
                    name = self._text(left, content)

                    # Check if this looks like a field assignment
                    right = expr.children[-1] if len(expr.children) > 1 else None
                    if right:
                        right_text = self._text(right, content).strip()

                        # Extract type annotation from field() call or direct assignment
                        type_annotation = ""
                        default = None
                        default_factory = None

                        if right_text.startswith("field("):
                            # field(default_factory=list)
                            if "default_factory=" in right_text:
                                factory_match = (
                                    right_text.split("default_factory=")[1]
                                    .split(",")[0]
                                    .split(")")[0]
                                )
                                default_factory = factory_match.strip()
                        else:
                            # Direct value assignment
                            default = right_text

                        return FieldInfo(
                            name=name,
                            type_annotation=type_annotation,
                            default=default,
                            default_factory=default_factory,
                        )
        return None

    def _extract_class_attribute(self, node, content: str) -> Optional[AttributeInfo]:
        """Extract class attribute from self.x = ... assignment."""
        if node.children:
            expr = node.children[0]
            if expr.type == "assignment":
                left = expr.children[0] if expr.children else None
                if left and left.type == "attribute":
                    obj = None
                    attr = None
                    try:
                        obj = left.child_by_field_name("object")
                        attr = left.child_by_field_name("attribute")
                    except Exception:
                        obj = None
                        attr = None

                    if obj is None and left.children:
                        obj = left.children[0]

                    if attr is None:
                        for sub in reversed(getattr(left, "children", []) or []):
                            if sub.type == "identifier":
                                attr = sub
                                break

                    if (
                        obj
                        and attr
                        and obj.type == "identifier"
                        and self._text(obj, content) == "self"
                        and attr.type == "identifier"
                    ):
                        attr_name = self._text(attr, content)

                        # Try to infer type from the assignment
                        type_annotation = ""
                        right = expr.children[-1] if len(expr.children) > 1 else None
                        if right:
                            right_text = self._text(right, content).strip()
                            # Simple type inference
                            if right_text in ("[]", "list()", "dict()", "{}"):
                                type_annotation = (
                                    "List" if right_text in ("[]", "list()") else "Dict"
                                )

                        return AttributeInfo(
                            name=attr_name,
                            type_annotation=type_annotation,
                            set_in_init=True,
                        )
        return None

    def _extract_init_attributes(self, func_node, content: str) -> List[AttributeInfo]:
        """Extract self.x = ... assignments from __init__ method body."""
        attributes = []
        seen_names = set()

        def scan_block(block_node):
            """Recursively scan block for self.x assignments."""
            if not block_node:
                return
            for child in block_node.children:
                if child.type == "expression_statement":
                    attr = self._extract_class_attribute(child, content)
                    if attr and attr.name not in seen_names:
                        seen_names.add(attr.name)
                        attributes.append(attr)
                # Also scan nested blocks (if/for/while/try)
                elif child.type in (
                    "if_statement",
                    "for_statement",
                    "while_statement",
                    "try_statement",
                ):
                    for sub in child.children:
                        if sub.type == "block":
                            scan_block(sub)

        body = self._find_child(func_node, "block")
        scan_block(body)
        return attributes[:CONSTANT_15]  # Limit to CONSTANT_15 attributes

    def _extract_class_property(self, node, content: str) -> Optional[str]:
        """Extract class-level property from annotated assignment."""
        try:
            stmt_text = self._text(node, content).strip()
        except Exception:
            return None

        # Match annotated assignment: "name: Type" or "name: Type = value"
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^=]+?)(?:\s*=.*)?$", stmt_text)
        if m:
            name = m.group(1)
            type_ann = m.group(2).strip()
            return f"{name}: {type_ann}"
        return None

    def _extract_py_import(self, node, content: str) -> List[str]:
        """Extract import statement."""
        imports = []
        for c in node.children:
            if c.type == "dotted_name":
                imports.append(self._text(c, content))
            elif c.type == "aliased_import":
                n = self._find_child(c, "dotted_name")
                if n:
                    imports.append(self._text(n, content))
        return imports

    def _extract_py_from_import(self, node, content: str) -> List[str]:
        """Extract from ... import ... statement."""
        imports = []
        module_parts = []
        seen_import_kw = False
        for c in node.children:
            if c.type == "import":
                seen_import_kw = True
                continue

            if not seen_import_kw:
                if c.type == "import_prefix":
                    module_parts.append(self._text(c, content))
                elif c.type in ("relative_import", "relative_import_statement"):
                    module_parts.append(self._text(c, content))
                elif c.type == "dotted_name":
                    module_parts.append(self._text(c, content))

        module = "".join(module_parts).strip().lstrip(".")

        collecting = False
        for c in node.children:
            if c.type == "import":
                collecting = True
                continue
            if not collecting:
                continue
            if c.type == "identifier":
                name = self._text(c, content)
                imports.append(_combine_import_name(module, name))
            elif c.type == "dotted_name":
                name = self._text(c, content)
                imports.append(_combine_import_name(module, name))
            elif c.type == "aliased_import":
                n = self._find_child(c, "identifier")
                if n:
                    name = self._text(n, content)
                    imports.append(_combine_import_name(module, name))
        return imports

    def _extract_py_constant(self, node, content: str) -> Optional[ConstantInfo]:
        """Extract constant (UPPERCASE assignment) with value."""
        stmt_text = ""
        try:
            stmt_text = self._text(node, content).strip()
        except Exception:
            stmt_text = ""

        # node is expression_statement, check if it contains assignment
        if node.children:
            expr = node.children[0]
            if expr.type == "assignment":
                left = expr.children[0] if expr.children else None
                right = expr.children[-1] if len(expr.children) > 1 else None
                if left and left.type == "identifier":
                    name = self._text(left, content)
                    if name.isupper():  # Convention: CONSTANTS are UPPERCASE
                        const = ConstantInfo(name=name)

                        # Best-effort type annotation from annotated assignment: NAME: Type = ...
                        if stmt_text:
                            m = re.match(
                                r"^\s*([A-Z][A-Z0-9_]*)\s*:\s*([^=]+?)\s*=\s*.+$",
                                stmt_text,
                            )
                            if m:
                                const.type_annotation = (m.group(2) or "").strip()

                        # Get the value
                        if right:
                            value_text = self._text(right, content).strip()
                            const.value = _truncate_constant_value(value_text)

                            # Infer type if not provided
                            if not getattr(const, "type_annotation", ""):
                                t = ""
                                vt = value_text.strip()
                                if vt.startswith("{"):
                                    t = "Dict"
                                elif vt.startswith("["):
                                    t = "List"
                                elif vt.startswith("("):
                                    t = "Tuple"
                                elif vt in ("True", "False"):
                                    t = "bool"
                                elif re.match(r"^-?\d+$", vt):
                                    t = "int"
                                elif re.match(r"^-?\d+\.\d+", vt):
                                    t = "float"
                                elif (vt.startswith('"') and vt.endswith('"')) or (
                                    vt.startswith("'") and vt.endswith("'")
                                ):
                                    t = "str"
                                const.type_annotation = t

                            # For dictionaries, extract keys
                            if value_text.startswith("{") and value_text.endswith("}"):
                                # Simple regex to extract keys
                                keys = re.findall(
                                    r"'([^']+)'|'([^']+)'", value_text[:CONSTANT_500]
                                )
                                const.value_keys = [
                                    k for pair in keys for k in pair if k
                                ][:10]

                        return const
        return None

    def _extract_conditional_imports(self, node, content: str) -> List[str]:
        """Extract imports from try/except blocks."""
        imports = []

        # Find the try body
        try_body = self._find_child(node, "block")
        if try_body:
            for child in try_body.children:
                if child.type == "import_statement":
                    imports.extend(self._extract_py_import(child, content))
                elif child.type in (
                    "import_from_statement",
                    "from_import_statement",
                    "import_from",
                ):
                    imports.extend(self._extract_py_from_import(child, content))

        return imports

    def _parse_js_ts(
        self, filepath: str, content: str, tree, language: str
    ) -> ModuleInfo:
        """Parse JavaScript/TypeScript source using Tree-sitter AST."""
        root = tree.root_node
        imports, classes, functions, types, constants, exports = [], [], [], [], [], []
        docstring = None
        seen_fn_names: set = set()

        def _add_func(func):
            if func and func.name not in seen_fn_names:
                functions.append(func)
                seen_fn_names.add(func.name)

        for child in root.children:
            node_type = child.type

            # Imports
            if node_type == "import_statement":
                for c in child.children:
                    if c.type == "string":
                        imports.append(self._text(c, content).strip("\"'"))

            # CommonJS require imports
            elif node_type in ("lexical_declaration", "variable_declaration"):
                self._extract_js_require_imports(child, content, imports)
                func = self._extract_js_var_fn(child, content)
                _add_func(func)
                const = self._extract_js_constant(child, content)
                if const:
                    constants.append(const)

            # Exports
            elif node_type == "export_statement":
                for c in child.children:
                    if c.type == "class_declaration":
                        cls = self._extract_js_class(c, content)
                        if cls:
                            classes.append(cls)
                            exports.append(cls.name)
                    elif c.type == "function_declaration":
                        func = self._extract_js_function(c, content)
                        if func:
                            _add_func(func)
                            exports.append(func.name)
                    elif c.type in ("lexical_declaration", "variable_declaration"):
                        func = self._extract_js_var_fn(c, content)
                        if func:
                            _add_func(func)
                            exports.append(func.name)
                    elif c.type in ("interface_declaration", "type_alias_declaration"):
                        t = self._extract_ts_type(c, content)
                        if t:
                            types.append(t)
                            exports.append(t.name)
                    elif c.type == "enum_declaration":
                        t = self._extract_ts_enum(c, content)
                        if t:
                            types.append(t)
                            exports.append(t.name)
                    elif c.type == "export_clause":
                        for spec in c.children:
                            if spec.type == "export_specifier":
                                name_node = self._find_child(spec, "identifier")
                                if name_node:
                                    exports.append(self._text(name_node, content))

            # Non-exported declarations
            elif node_type == "class_declaration":
                cls = self._extract_js_class(child, content)
                if cls:
                    classes.append(cls)
                    exports.append(cls.name)
            elif node_type == "function_declaration":
                func = self._extract_js_function(child, content)
                _add_func(func)
                if func:
                    exports.append(func.name)
            elif node_type in ("interface_declaration", "type_alias_declaration"):
                t = self._extract_ts_type(child, content)
                if t:
                    types.append(t)
                    exports.append(t.name)

            # expression_statement: IIFEs, module.exports, assignments
            elif node_type == "expression_statement":
                self._extract_from_expression_stmt(
                    child, content, functions, exports, seen_fn_names
                )

            # Leading comment as docstring
            elif node_type == "comment" and not docstring:
                docstring = self._extract_js_comment(child, content)

        # Walk entire tree for nested functions (inside other function bodies)
        self._walk_nested_functions(root, content, functions, seen_fn_names)

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language=language,
            imports=imports[:PORT_20],
            exports=list(set(exports)),
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=docstring[:100] if docstring else None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("//")]
            ),
        )

    def _extract_js_class(self, node, content: str) -> Optional[ClassInfo]:
        """Extract JS/TS class from AST node."""
        name_node = self._find_child(node, "type_identifier") or self._find_child(
            node, "identifier"
        )
        if not name_node:
            return None
        name = self._text(name_node, content)

        # Base classes
        bases = []
        heritage = self._find_child(node, "class_heritage")
        if heritage:
            for c in heritage.children:
                if c.type == "identifier":
                    bases.append(self._text(c, content))

        # Methods
        methods = []
        body = self._find_child(node, "class_body")
        if body:
            for c in body.children:
                if c.type == "method_definition":
                    m = self._extract_js_method(c, content)
                    if m:
                        methods.append(m)

        return ClassInfo(
            name=name,
            bases=bases,
            docstring=None,
            methods=methods,
            properties=[],
            is_interface=False,
            is_abstract="abstract" in self._text(node, content)[:CONSTANT_50],
            generic_params=[],
        )

    def _extract_js_method(self, node, content: str) -> Optional[FunctionInfo]:
        """Extract JS/TS method from AST node."""
        name_node = self._find_child(node, "property_identifier")
        if not name_node:
            return None
        name = self._text(name_node, content)

        node_text = self._text(node, content)[:100]
        is_async = "async" in node_text.split(name)[0] if name in node_text else False
        is_static = "static" in node_text.split(name)[0] if name in node_text else False

        # Parameters
        params = []
        params_node = self._find_child(node, "formal_parameters")
        if params_node:
            params = self._extract_js_params(params_node, content)

        # Return type
        return_type = None
        type_ann = self._find_child(node, "type_annotation")
        if type_ann:
            return_type = self._text(type_ann, content).lstrip(":").strip()

        return FunctionInfo(
            name=name,
            params=params[:CONSTANT_8],
            return_type=return_type,
            docstring=None,
            calls=[],
            raises=[],
            complexity=1,
            lines=node.end_point[0] - node.start_point[0] + 1,
            decorators=[],
            is_async=is_async,
            is_static=is_static,
            is_private=name.startswith("_") or name.startswith("#"),
            intent=self.intent_gen.generate(name),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        )

    def _extract_js_function(self, node, content: str) -> Optional[FunctionInfo]:
        """Extract JS/TS function from AST node."""
        name_node = self._find_child(node, "identifier")
        if not name_node:
            return None
        name = self._text(name_node, content)
        is_async = self._text(node, content)[:CONSTANT_50].strip().startswith("async")

        params = []
        params_node = self._find_child(node, "formal_parameters")
        if params_node:
            params = self._extract_js_params(params_node, content)

        return_type = None
        type_ann = self._find_child(node, "type_annotation")
        if type_ann:
            return_type = self._text(type_ann, content).lstrip(":").strip()

        return FunctionInfo(
            name=name,
            params=params[:CONSTANT_8],
            return_type=return_type,
            docstring=None,
            calls=[],
            raises=[],
            complexity=1,
            lines=node.end_point[0] - node.start_point[0] + 1,
            decorators=[],
            is_async=is_async,
            is_static=False,
            is_private=name.startswith("_"),
            intent=self.intent_gen.generate(name),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        )

    def _extract_js_var_fn(self, node, content: str) -> Optional[FunctionInfo]:
        """Extract arrow function or function expression assigned to const/let/var."""
        for c in node.children:
            if c.type == "variable_declarator":
                name_node = self._find_child(c, "identifier")
                if not name_node:
                    continue
                # Arrow function: const foo = (...) => { ... }
                fn_node = self._find_child(c, "arrow_function")
                # Function expression: const foo = function(...) { ... }
                if fn_node is None:
                    fn_node = self._find_child(c, "function")
                # Also handle: const foo = async function(...) { ... }  (via function_expression)
                if fn_node is None:
                    fn_node = self._find_child(c, "function_expression")
                if fn_node is None:
                    # Check for call_expression wrapping function (e.g. memoize(function...))
                    continue
                name = self._text(name_node, content)
                fn_text = self._text(fn_node, content)[:CONSTANT_50]
                is_async = fn_text.strip().startswith("async")
                params = []
                pn = self._find_child(fn_node, "formal_parameters")
                if pn:
                    params = self._extract_js_params(pn, content)
                return_type = None
                type_ann = self._find_child(fn_node, "type_annotation")
                if type_ann:
                    return_type = self._text(type_ann, content).lstrip(":").strip()
                return FunctionInfo(
                    name=name,
                    params=params[:CONSTANT_8],
                    return_type=return_type,
                    docstring=None,
                    calls=[],
                    raises=[],
                    complexity=1,
                    lines=node.end_point[0] - node.start_point[0] + 1,
                    decorators=[],
                    is_async=is_async,
                    is_static=False,
                    is_private=name.startswith("_"),
                    intent=self.intent_gen.generate(name),
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
        return None

    def _extract_js_arrow_fn(self, node, content: str) -> Optional[FunctionInfo]:
        """Extract arrow function assigned to const (backward compat alias)."""
        return self._extract_js_var_fn(node, content)

    def _extract_js_require_imports(self, node, content: str, imports: list):
        """Extract CommonJS require() imports from variable declarations."""
        for c in node.children:
            if c.type == "variable_declarator":
                # const fs = require('fs')
                val = self._find_child(c, "call_expression")
                if val:
                    fn = self._find_child(val, "identifier")
                    if fn and self._text(fn, content) == "require":
                        args = self._find_child(val, "arguments")
                        if args:
                            for arg in args.children:
                                if arg.type == "string":
                                    imports.append(
                                        self._text(arg, content).strip("\"'")
                                    )

    def _extract_from_expression_stmt(
        self, node, content: str, functions: list, exports: list, seen_fn_names: set
    ):
        """Extract functions/exports from expression_statement nodes.

        Handles:
        - IIFE: (function main() { ... })()
        - module.exports = { name1, name2 }
        - module.exports.foo = function() {}
        - exports.foo = function() {}
        """
        if not node.children:
            return
        expr = node.children[0]

        # IIFE: (function name() { ... })() or (function name() { ... }())
        if expr.type == "call_expression":
            callee = self._find_child(expr, "parenthesized_expression")
            if callee:
                for sub in callee.children:
                    if sub.type == "function_expression" or sub.type == "function":
                        name_node = self._find_child(sub, "identifier")
                        if name_node:
                            name = self._text(name_node, content)
                            if name not in seen_fn_names:
                                params = []
                                pn = self._find_child(sub, "formal_parameters")
                                if pn:
                                    params = self._extract_js_params(pn, content)
                                fn_text = self._text(sub, content)[:CONSTANT_50]
                                functions.append(
                                    FunctionInfo(
                                        name=name,
                                        params=params[:CONSTANT_8],
                                        return_type=None,
                                        docstring=None,
                                        calls=[],
                                        raises=[],
                                        complexity=1,
                                        lines=sub.end_point[0] - sub.start_point[0] + 1,
                                        decorators=[],
                                        is_async=fn_text.strip().startswith("async"),
                                        is_static=False,
                                        is_private=name.startswith("_"),
                                        intent=self.intent_gen.generate(name),
                                        start_line=sub.start_point[0] + 1,
                                        end_line=sub.end_point[0] + 1,
                                    )
                                )
                                seen_fn_names.add(name)
            # Also check direct function call: main()
            fn_node = self._find_child(expr, "identifier")
            if not fn_node:
                return

        # module.exports = { ... } or module.exports.foo = ...
        if expr.type == "assignment_expression":
            left = self._find_child(expr, "member_expression")
            right = None
            for c in expr.children:
                if c.type == "object":
                    right = c
                    break
                if c.type in ("function_expression", "function", "arrow_function"):
                    right = c
                    break

            if left:
                left_text = self._text(left, content)
                # module.exports = { User, Product, ... }
                if (
                    left_text in ("module.exports", "exports")
                    and right
                    and right.type == "object"
                ):
                    for prop in right.children:
                        if prop.type == "shorthand_property_identifier":
                            exports.append(self._text(prop, content))
                        elif prop.type == "pair":
                            key = self._find_child(prop, "property_identifier")
                            if key:
                                exports.append(self._text(key, content))

                # module.exports.foo = function() {} or exports.foo = function() {}
                elif left_text.startswith("module.exports.") or left_text.startswith(
                    "exports."
                ):
                    name = left_text.split(".")[-1]
                    exports.append(name)
                    if right and right.type in (
                        "function_expression",
                        "function",
                        "arrow_function",
                    ):
                        if name not in seen_fn_names:
                            params = []
                            pn = self._find_child(right, "formal_parameters")
                            if pn:
                                params = self._extract_js_params(pn, content)
                            functions.append(
                                FunctionInfo(
                                    name=name,
                                    params=params[:CONSTANT_8],
                                    return_type=None,
                                    docstring=None,
                                    calls=[],
                                    raises=[],
                                    complexity=1,
                                    lines=right.end_point[0] - right.start_point[0] + 1,
                                    decorators=[],
                                    is_async=False,
                                    is_static=False,
                                    is_private=name.startswith("_"),
                                    intent=self.intent_gen.generate(name),
                                    start_line=right.start_point[0] + 1,
                                    end_line=right.end_point[0] + 1,
                                )
                            )
                            seen_fn_names.add(name)

    def _walk_nested_functions(
        self, root, content: str, functions: list, seen_fn_names: set
    ):
        """Recursively walk AST to find nested function declarations.

        Finds function declarations inside other function bodies (not at top level).
        Skips top-level nodes (already processed) and class methods (handled by class extraction).
        """

        def _walk(node, depth):
            if depth > PORT_20:
                return
            for child in node.children:
                if child.type == "function_declaration":
                    # Only add if not already seen (top-level ones already added)
                    name_node = self._find_child(child, "identifier")
                    if name_node:
                        name = self._text(name_node, content)
                        if name not in seen_fn_names:
                            func = self._extract_js_function(child, content)
                            if func:
                                functions.append(func)
                                seen_fn_names.add(name)
                # Recurse into blocks, but skip class bodies (methods handled separately)
                if child.type in (
                    "statement_block",
                    "if_statement",
                    "for_statement",
                    "for_in_statement",
                    "while_statement",
                    "try_statement",
                    "catch_clause",
                    "switch_statement",
                    "switch_body",
                    "switch_case",
                    "switch_default",
                    "function_declaration",
                    "arrow_function",
                    "function_expression",
                    "function",
                    "export_statement",
                    "labeled_statement",
                    "parenthesized_expression",
                    "call_expression",
                    "expression_statement",
                    "arguments",
                    "lexical_declaration",
                    "variable_declaration",
                    "variable_declarator",
                ):
                    _walk(child, depth + 1)

        # Start from root children to skip depth 0 (already handled by main loop)
        for child in root.children:
            if child.type in (
                "function_declaration",
                "export_statement",
                "lexical_declaration",
                "variable_declaration",
                "expression_statement",
            ):
                _walk(child, 1)

    def _extract_js_params(self, params_node, content: str) -> List[str]:
        """Extract JS/TS function parameters."""
        params = []
        for c in params_node.children:
            if c.type == "identifier":
                params.append(self._text(c, content))
            elif c.type == "required_parameter":
                n = self._find_child(c, "identifier")
                t = self._find_child(c, "type_annotation")
                if n:
                    p = self._text(n, content)
                    if t:
                        p += self._text(t, content)
                    params.append(p)
            elif c.type == "optional_parameter":
                n = self._find_child(c, "identifier")
                if n:
                    params.append(self._text(n, content) + "?")
        return params

    def _extract_ts_type(self, node, content: str) -> Optional[TypeInfo]:
        """Extract TypeScript interface or type alias."""
        name_node = self._find_child(node, "type_identifier") or self._find_child(
            node, "identifier"
        )
        if not name_node:
            return None
        name = self._text(name_node, content)
        kind = "interface" if node.type == "interface_declaration" else "type"
        return TypeInfo(
            name=name, kind=kind, definition=self._text(node, content)[:100]
        )

    def _extract_ts_enum(self, node, content: str) -> Optional[TypeInfo]:
        """Extract TypeScript enum."""
        name_node = self._find_child(node, "identifier")
        if not name_node:
            return None
        name = self._text(name_node, content)
        values: List[str] = []
        try:
            text = self._text(node, content)
            m = re.search(r"\{(?P<body>.*)\}", text, flags=re.S)
            body = m.group("body") if m else ""
            for mm in re.finditer(
                r"\b([A-Za-z_][A-Za-z0-9_]*)\b\s*(?:=\s*([^,\n\r\}]+))?", body
            ):
                mem = mm.group(1)
                if mem in ("enum", "const", "export"):
                    continue
                rhs = (mm.group(2) or "").strip()
                values.append(f"{mem}={rhs}" if rhs else mem)
                if len(values) >= CONSTANT_25:
                    break
        except Exception:
            values = []
        return TypeInfo(name=name, kind="enum", definition="", values=values or None)

    def _extract_js_constant(self, node, content: str) -> Optional[str]:
        """Extract constant (UPPERCASE const)."""
        for c in node.children:
            if c.type == "variable_declarator":
                n = self._find_child(c, "identifier")
                if n:
                    name = self._text(n, content)
                    if name.isupper():
                        return name
        return None

    def _extract_js_comment(self, node, content: str) -> Optional[str]:
        """Extract JS comment content."""
        text = self._text(node, content)
        if text.startswith("/**"):
            lines = text[CONSTANT_3:-2].split("\n")
            clean = [
                l.strip().lstrip("*").strip()
                for l in lines
                if l.strip().lstrip("*").strip() and not l.strip().startswith("@")
            ]
            return " ".join(clean)[:100] if clean else None
        elif text.startswith("//"):
            return text[2:].strip()[:100]
        return None

    # Helper methods
    def _find_child(self, node, type_name: str):
        """Find first child of given type."""
        for c in node.children:
            if c.type == type_name:
                return c
        return None

    def _text(self, node, content: str) -> str:
        """Get text content of node.

        Tree-sitter returns byte offsets, so we must slice bytes, not chars.
        """
        content_bytes = content.encode("utf8")
        return content_bytes[node.start_byte : node.end_byte].decode(
            "utf8", errors="replace"
        )

    def _extract_string(self, node, content: str) -> str:
        """Extract string content without quotes."""
        text = self._text(node, content)
        if text.startswith('"""') or text.startswith("'''"):
            return text[CONSTANT_3:-CONSTANT_3].strip()
        elif text.startswith('"') or text.startswith("'"):
            return text[1:-1].strip()
        return text

    def _truncate_docstring(
        self, docstring: Optional[str], max_len: int = CONSTANT_80
    ) -> Optional[str]:
        """Truncate docstring to first sentence or max_len characters.

        Args:
            docstring: Full docstring text
            max_len: Maximum length (default 80)

        Returns:
            Truncated docstring or None
        """
        if not docstring:
            return None
        # Get first line/sentence
        text = docstring.strip()
        # Find first sentence end
        for end in [". ", ".\n", ".\t"]:
            idx = text.find(end)
            if idx > 0 and idx < max_len:
                return text[: idx + 1].strip()
        # No sentence end found, truncate at max_len
        if len(text) > max_len:
            return text[:max_len].rstrip() + "..."
        return text


class UniversalParser:
    """
    Fallback parser using Python AST and regex.

    Used when Tree-sitter is not available. Provides reasonable
    accuracy for Python (using built-in AST) and basic support
    for JavaScript/TypeScript using regex patterns.

    Example:
        >>> parser = UniversalParser()
        >>> module = parser.parse('main.py', content, 'python')
    """

    def __init__(self):
        """Initialize the universal parser."""
        self.intent_gen = EnhancedIntentGenerator()

    def parse(self, filepath: str, content: str, language: str) -> Optional[ModuleInfo]:
        """
        Parse a source file using AST or regex.

        Args:
            filepath: Relative path to the file
            content: File content as string
            language: Programming language

        Returns:
            ModuleInfo if parsing succeeds, None otherwise
        """
        if isinstance(filepath, str) and isinstance(content, str):
            if "\n" in filepath and "\n" not in content:
                filepath, content = content, filepath

        if language == "python":
            return self._parse_python(filepath, content)
        if language in ("javascript", "typescript"):
            return self._parse_js_ts(filepath, content, language)
        if language == "go":
            return self._parse_go(filepath, content)
        if language == "rust":
            return self._parse_rust(filepath, content)
        if language == "java":
            return self._parse_java(filepath, content)
        if language == "csharp":
            return self._parse_csharp(filepath, content)
        if language == "sql":
            return self._parse_sql(filepath, content)
        return None

    def _parse_python(self, filepath: str, content: str) -> Optional[ModuleInfo]:
        """Parse Python using built-in AST."""
        try:
            tree = ast.parse(content, filename=filepath or "<unknown>")
        except SyntaxError:
            lines = content.split("\n")
            return ModuleInfo(
                path=filepath,
                language="python",
                imports=[],
                exports=[],
                classes=[],
                functions=[],
                types=[],
                constants=[],
                docstring=None,
                lines_total=len(lines),
                lines_code=len([l for l in lines if l.strip()]),
            )

        imports, classes, functions, types, constants = [], [], [], [], []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                imports.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if alias.name == "*":
                        if module:
                            imports.append(f"{module}.*")
                        continue
                    imports.append(_combine_import_name(module, alias.name))
            elif isinstance(node, ast.ClassDef):
                cls = self._extract_ast_class(node)
                if cls:
                    classes.append(cls)
                enum_type = self._extract_ast_enum(node)
                if enum_type:
                    types.append(enum_type)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._extract_ast_function(node)
                if func:
                    functions.append(func)
            elif isinstance(node, ast.Assign):
                const = self._extract_ast_constant(node, content)
                if const:
                    constants.append(const)

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                if name and name.isupper() and node.value is not None:
                    const = ConstantInfo(name=name)
                    try:
                        const.type_annotation = (
                            self._ann_str(node.annotation) if node.annotation else ""
                        )
                    except Exception:
                        const.type_annotation = ""
                    try:
                        const.value = _truncate_constant_value(
                            ast.unparse(node.value) if hasattr(ast, "unparse") else ""
                        )
                    except Exception:
                        const.value = None
                    if const.value:
                        constants.append(const)

        exports = [c.name for c in classes if not c.name.startswith("_")]
        exports += [f.name for f in functions if not f.name.startswith("_")]
        lines = content.split("\n")

        return ModuleInfo(
            path=filepath,
            language="python",
            imports=imports[:PORT_20],
            exports=exports,
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=ast.get_docstring(tree)[:100]
            if ast.get_docstring(tree)
            else None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("#")]
            ),
        )

    def _extract_ast_enum(self, node: ast.ClassDef) -> Optional[TypeInfo]:
        """Extract Enum values from Python AST class."""
        try:
            base_names = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    base_names.append(b.id)
                elif isinstance(b, ast.Attribute):
                    base_names.append(b.attr)
            if not any(
                n.endswith("Enum") or n in ("Enum", "IntEnum", "StrEnum")
                for n in base_names
            ):
                return None

            values: List[str] = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            mem = target.id
                            if not mem or mem.startswith("_"):
                                continue
                            rhs = ""
                            try:
                                rhs = (
                                    ast.unparse(item.value)
                                    if hasattr(ast, "unparse")
                                    else ""
                                )
                            except Exception:
                                rhs = ""
                            values.append(f"{mem}={rhs}" if rhs else mem)
                            if len(values) >= CONSTANT_25:
                                break
                elif isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    mem = item.target.id
                    if not mem or mem.startswith("_"):
                        continue
                    rhs = ""
                    if item.value is not None:
                        try:
                            rhs = (
                                ast.unparse(item.value)
                                if hasattr(ast, "unparse")
                                else ""
                            )
                        except Exception:
                            rhs = ""
                    values.append(f"{mem}={rhs}" if rhs else mem)
                if len(values) >= CONSTANT_25:
                    break

            return TypeInfo(
                name=node.name, kind="enum", definition="", values=values or None
            )
        except Exception:
            return None

    def _extract_ast_function(self, node) -> FunctionInfo:
        """Extract function from Python AST node."""
        is_async = isinstance(node, ast.AsyncFunctionDef)

        # Extract parameters with defaults
        params = []
        defaults = []
        for arg in node.args.args:
            p = arg.arg
            if arg.annotation:
                p += ":" + self._ann_str(arg.annotation)
            params.append(p)

        # Extract default values
        for default in node.args.defaults:
            if isinstance(default, ast.Constant):
                defaults.append(repr(default.value))
            elif isinstance(default, ast.Str):
                defaults.append(repr(default.s))
            elif isinstance(default, ast.NameConstant):
                defaults.append(str(default.value))
            elif isinstance(default, ast.Name):
                defaults.append(default.id)
            else:
                defaults.append(
                    str(
                        ast.unparse(default)
                        if hasattr(ast, "unparse")
                        else repr(default)
                    )
                )

        # Align defaults with parameters (defaults apply to last N parameters)
        param_defaults = [None] * (len(params) - len(defaults)) + defaults

        # Create enhanced params with defaults
        enhanced_params = []
        for i, param in enumerate(params[:CONSTANT_8]):
            if i < len(param_defaults) and param_defaults[i]:
                enhanced_params.append(f"{param}={param_defaults[i]}")
            else:
                enhanced_params.append(param)

        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)

        docstring = ast.get_docstring(node)

        calls: List[str] = []
        raises: List[str] = []
        complexity = 1
        try:
            calls, raises, complexity = _analyze_python_function_node(node)
        except Exception:
            pass
        return FunctionInfo(
            name=node.name,
            params=enhanced_params,
            return_type=self._ann_str(node.returns) if node.returns else None,
            docstring=docstring[:100] if docstring else None,
            calls=calls,
            raises=raises,
            complexity=complexity,
            lines=node.end_lineno - node.lineno + 1
            if hasattr(node, "end_lineno")
            else 1,
            decorators=decorators,
            is_async=is_async,
            is_static="staticmethod" in decorators,
            is_private=node.name.startswith("_") and not node.name.startswith("__"),
            intent=self.intent_gen.generate(node.name, docstring),
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
        )

    def _extract_ast_class(self, node: ast.ClassDef) -> ClassInfo:
        """Extract class from Python AST node."""
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)

        methods = []
        properties = []

        # Check if this is a dataclass
        is_dataclass = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
            or (
                isinstance(d, ast.Call)
                and (
                    (isinstance(d.func, ast.Name) and d.func.id == "dataclass")
                    or (
                        isinstance(d.func, ast.Attribute) and d.func.attr == "dataclass"
                    )
                )
            )
            for d in node.decorator_list
        )

        fields: List[FieldInfo] = []
        attributes: List[AttributeInfo] = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_ast_function(item))
                # Best-effort instance attribute extraction from __init__
                if item.name == "__init__":
                    try:
                        for stmt in getattr(item, "body", []) or []:
                            # self.x = ...
                            if isinstance(stmt, ast.Assign):
                                for tgt in stmt.targets:
                                    if (
                                        isinstance(tgt, ast.Attribute)
                                        and isinstance(tgt.value, ast.Name)
                                        and tgt.value.id == "self"
                                    ):
                                        attr_name = tgt.attr
                                        if attr_name:
                                            attributes.append(
                                                AttributeInfo(
                                                    name=attr_name,
                                                    type_annotation="",
                                                    set_in_init=True,
                                                )
                                            )
                    except Exception:
                        pass
            # Extract class attributes (properties) - critical for dataclasses
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                prop_name = item.target.id
                prop_type = self._ann_str(item.annotation) if item.annotation else "Any"
                properties.append(f"{prop_name}: {prop_type}")

                # Dataclass fields should include name+type (+ default info when available)
                if is_dataclass:
                    default = None
                    default_factory = None
                    try:
                        if getattr(item, "value", None) is not None:
                            v = item.value
                            # dataclasses.field(default_factory=...)
                            if isinstance(v, ast.Call) and (
                                (isinstance(v.func, ast.Name) and v.func.id == "field")
                                or (
                                    isinstance(v.func, ast.Attribute)
                                    and v.func.attr == "field"
                                )
                            ):
                                for kw in getattr(v, "keywords", []) or []:
                                    if kw.arg == "default_factory":
                                        default_factory = (
                                            ast.unparse(kw.value)
                                            if hasattr(ast, "unparse")
                                            else None
                                        )
                                    elif kw.arg == "default":
                                        default = (
                                            ast.unparse(kw.value)
                                            if hasattr(ast, "unparse")
                                            else None
                                        )
                            else:
                                default = (
                                    ast.unparse(v) if hasattr(ast, "unparse") else None
                                )
                    except Exception:
                        default = None
                        default_factory = None

                    fields.append(
                        FieldInfo(
                            name=prop_name,
                            type_annotation=prop_type,
                            default=default,
                            default_factory=default_factory,
                        )
                    )
            # Also handle simple assignments
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        properties.append(target.id)

        # Extract decorators
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(dec.attr)

        return ClassInfo(
            name=node.name,
            bases=bases,
            decorators=decorators,
            docstring=ast.get_docstring(node)[:100]
            if ast.get_docstring(node)
            else None,
            is_dataclass=is_dataclass,
            fields=fields,
            attributes=attributes,
            methods=methods,
            properties=properties,
            is_interface=False,
            is_abstract="ABC" in bases,
            generic_params=[],
        )

    def _extract_ast_constant(
        self, node: ast.Assign, content: str
    ) -> Optional[ConstantInfo]:
        """Extract ConstantInfo from an AST assignment node if applicable."""
        if not node.targets:
            return None
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not target.id.isupper():
            return None

        const = ConstantInfo(name=target.id)
        # Type inference
        try:
            v = node.value
            if isinstance(v, ast.Dict):
                const.type_annotation = "Dict"
            elif isinstance(v, ast.List):
                const.type_annotation = "List"
            elif isinstance(v, ast.Tuple):
                const.type_annotation = "Tuple"
            elif isinstance(v, ast.Constant):
                if isinstance(v.value, bool):
                    const.type_annotation = "bool"
                elif isinstance(v.value, int):
                    const.type_annotation = "int"
                elif isinstance(v.value, float):
                    const.type_annotation = "float"
                elif isinstance(v.value, str):
                    const.type_annotation = "str"
        except Exception:
            pass
        value_text = self._format_ast_value(node.value, content)
        if value_text:
            const.value = _truncate_constant_value(value_text)

        if isinstance(node.value, ast.Dict):
            keys = []
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.append(key.value)
            if keys:
                const.value_keys = keys[:10]
        return const

    def _format_ast_value(self, value_node: ast.AST, content: str) -> str:
        """Best-effort string representation of an AST value node."""
        if value_node is None:
            return ""
        try:
            import ast

            if hasattr(ast, "unparse"):
                return ast.unparse(value_node)
        except Exception:
            pass
        try:
            segment = ast.get_source_segment(content, value_node)
            if segment:
                return segment
        except Exception:
            pass
        if isinstance(value_node, ast.Constant):
            return repr(value_node.value)
        return ""

    def _ann_str(self, node) -> str:
        """Convert AST annotation to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            base = self._ann_str(node.value)
            if isinstance(node.slice, ast.Tuple):
                args = ",".join(self._ann_str(e) for e in node.slice.elts)
            else:
                args = self._ann_str(node.slice)
            return f"{base}[{args}]"
        return "Any"

    def _parse_js_ts(self, filepath: str, content: str, language: str) -> ModuleInfo:
        """Parse JS/TS using regex patterns."""
        imports, classes, functions, types, constants, exports = [], [], [], [], [], []

        # Import patterns
        for m in re.finditer(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]", content):
            imports.append(m.group(1))

        # Re-export patterns (export * / export {...} from)
        for m in re.finditer(r"export\s+\*\s+from\s+['\"]([^'\"]+)['\"]", content):
            mod = m.group(1)
            imports.append(mod)
            exports.append(f"* from {mod}")

        for m in re.finditer(
            r"export\s+\*\s+as\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]", content
        ):
            name = m.group(1)
            mod = m.group(2)
            imports.append(mod)
            exports.append(f"* as {name} from {mod}")
            exports.append(name)

        for m in re.finditer(
            r"export\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]", content
        ):
            items = m.group(1)
            mod = m.group(2)
            imports.append(mod)
            for raw in (items or "").split(","):
                part = raw.strip()
                if not part:
                    continue
                if " as " in part:
                    exported = part.split(" as ", 1)[1].strip()
                else:
                    exported = part
                if exported:
                    exports.append(exported)

        # Local export list (export { A, B as C };)
        for m in re.finditer(r"export\s+\{([^}]+)\}\s*;", content):
            if "from" in m.group(0):
                continue
            items = m.group(1)
            for raw in (items or "").split(","):
                part = raw.strip()
                if not part:
                    continue
                if " as " in part:
                    exported = part.split(" as ", 1)[1].strip()
                else:
                    exported = part
                if exported:
                    exports.append(exported)

        # Class patterns
        for m in re.finditer(
            r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
            content,
        ):
            classes.append(
                ClassInfo(
                    name=m.group(1),
                    bases=[m.group(2)] if m.group(2) else [],
                    docstring=None,
                    methods=[],
                    properties=[],
                    is_interface=False,
                    is_abstract="abstract" in m.group(0),
                    generic_params=[],
                )
            )
            exports.append(m.group(1))

        # Function patterns
        for m in re.finditer(
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?",
            content,
        ):
            name = m.group(1)
            params = [p.strip() for p in (m.group(2) or "").split(",") if p.strip()][
                :CONSTANT_8
            ]
            functions.append(
                FunctionInfo(
                    name=name,
                    params=params,
                    return_type=m.group(CONSTANT_3).strip()
                    if m.group(CONSTANT_3)
                    else None,
                    docstring=None,
                    calls=[],
                    raises=[],
                    complexity=1,
                    lines=1,
                    decorators=[],
                    is_async="async" in m.group(0),
                    is_static=False,
                    is_private=name.startswith("_"),
                    intent=self.intent_gen.generate(name),
                )
            )
            exports.append(name)

        # Arrow function patterns (const/let/var)
        for m in re.finditer(
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*(?::\s*[^=]+)?\s*=>",
            content,
        ):
            name = m.group(1)
            if not any(f.name == name for f in functions):
                functions.append(
                    FunctionInfo(
                        name=name,
                        params=[],
                        return_type=None,
                        docstring=None,
                        calls=[],
                        raises=[],
                        complexity=1,
                        lines=1,
                        decorators=[],
                        is_async="async" in m.group(0),
                        is_static=False,
                        is_private=name.startswith("_"),
                        intent=self.intent_gen.generate(name),
                    )
                )
                exports.append(name)

        # Function expression patterns (const/let/var foo = function(...) {})
        for m in re.finditer(
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)",
            content,
        ):
            name = m.group(1)
            if not any(f.name == name for f in functions):
                params = [
                    p.strip() for p in (m.group(2) or "").split(",") if p.strip()
                ][:CONSTANT_8]
                functions.append(
                    FunctionInfo(
                        name=name,
                        params=params,
                        return_type=None,
                        docstring=None,
                        calls=[],
                        raises=[],
                        complexity=1,
                        lines=1,
                        decorators=[],
                        is_async="async" in m.group(0),
                        is_static=False,
                        is_private=name.startswith("_"),
                        intent=self.intent_gen.generate(name),
                    )
                )
                exports.append(name)

        # IIFE with named function: (function main() { ... })()
        for m in re.finditer(r"\(\s*function\s+(\w+)\s*\(([^)]*)\)", content):
            name = m.group(1)
            if not any(f.name == name for f in functions):
                params = [
                    p.strip() for p in (m.group(2) or "").split(",") if p.strip()
                ][:CONSTANT_8]
                functions.append(
                    FunctionInfo(
                        name=name,
                        params=params,
                        return_type=None,
                        docstring=None,
                        calls=[],
                        raises=[],
                        complexity=1,
                        lines=1,
                        decorators=[],
                        is_async=False,
                        is_static=False,
                        is_private=name.startswith("_"),
                        intent=self.intent_gen.generate(name),
                    )
                )

        # module.exports = { name1, name2, ... }
        m = re.search(r"module\.exports\s*=\s*\{([^}]+)\}", content)
        if m:
            for raw in m.group(1).split(","):
                part = raw.strip().split(":")[0].strip().split(" ")[0].strip()
                if part and re.match(r"^[A-Za-z_]\w*$", part):
                    if part not in exports:
                        exports.append(part)

        # Interface/Type patterns
        for m in re.finditer(r"(?:export\s+)?(interface|type)\s+(\w+)", content):
            types.append(TypeInfo(name=m.group(2), kind=m.group(1), definition=""))
            exports.append(m.group(2))

        # Constant patterns
        for m in re.finditer(r"const\s+([A-Z][A-Z0-9_]+)\s*=", content):
            constants.append(m.group(1))

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language=language,
            imports=imports[:PORT_20],
            exports=list(set(exports)),
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("//")]
            ),
        )

    def _parse_go(self, filepath: str, content: str) -> ModuleInfo:
        """Parse Go using regex patterns."""
        imports: List[str] = []
        classes: List[ClassInfo] = []
        functions: List[FunctionInfo] = []
        types: List[TypeInfo] = []
        constants: List[str] = []
        exports: List[str] = []

        for m in re.finditer(r"^package\s+(\w+)", content, re.MULTILINE):
            _ = m.group(1)

        for m in re.finditer(r'^import\s+\(?\s*"([^"]+)"', content, re.MULTILINE):
            imports.append(m.group(1))

        for m in re.finditer(r"^type\s+(\w+)\s+struct\b", content, re.MULTILINE):
            name = m.group(1)
            classes.append(ClassInfo(name=name))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="struct", definition=""))

        for m in re.finditer(r"^type\s+(\w+)\s+interface\b", content, re.MULTILINE):
            name = m.group(1)
            classes.append(ClassInfo(name=name, is_interface=True))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="interface", definition=""))

        for m in re.finditer(
            r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(([^)]*)\)\s*(\([^)]*\)|\w+)?",
            content,
            re.MULTILINE,
        ):
            name = m.group(1)
            params = [p.strip() for p in (m.group(2) or "").split(",") if p.strip()][
                :CONSTANT_8
            ]
            ret = (m.group(CONSTANT_3) or "").strip()
            functions.append(
                FunctionInfo(
                    name=name,
                    params=params,
                    return_type=ret,
                    docstring=None,
                    docstring_full=None,
                    calls=[],
                    raises=[],
                    decorators=[],
                    complexity=1,
                    lines=1,
                    is_async=False,
                    is_static=False,
                    is_classmethod=False,
                    is_property=False,
                    intent=self.intent_gen.generate(name),
                    start_line=0,
                    end_line=0,
                    is_private=False,
                )
            )
            exports.append(name)

        for m in re.finditer(r"^const\s+([A-Z][A-Za-z0-9_]*)\b", content, re.MULTILINE):
            constants.append(m.group(1))

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language="go",
            imports=imports[:PORT_20],
            exports=list(dict.fromkeys(exports))[:CONSTANT_50],
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("//")]
            ),
        )

    def _parse_rust(self, filepath: str, content: str) -> ModuleInfo:
        """Parse Rust using regex patterns."""
        imports: List[str] = []
        classes: List[ClassInfo] = []
        functions: List[FunctionInfo] = []
        types: List[TypeInfo] = []
        constants: List[str] = []
        exports: List[str] = []

        def _get_or_create_class(name: str) -> ClassInfo:
            for c in classes:
                if c.name == name:
                    return c
            c = ClassInfo(name=name)
            classes.append(c)
            return c

        def _find_matching_brace(src: str, start_idx: int) -> int:
            depth = 0
            in_str = False
            str_ch = ""
            i = start_idx
            while i < len(src):
                ch = src[i]
                if in_str:
                    if ch == "\\" and i + 1 < len(src):
                        i += 2
                        continue
                    if ch == str_ch:
                        in_str = False
                        str_ch = ""
                    i += 1
                    continue
                if ch in ('"', "'"):
                    in_str = True
                    str_ch = ch
                    i += 1
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
                i += 1
            return -1

        def _parse_rust_fn(match: re.Match, *, is_method: bool) -> FunctionInfo:
            name = match.group("name")
            params_raw = (match.group("params") or "").strip()
            ret = (match.group("ret") or "").strip()
            sig = match.group(0) or ""

            params = [p.strip() for p in params_raw.split(",") if p.strip()]
            params = params[:CONSTANT_8]

            is_pub = bool(re.search(r"\bpub\b", sig))
            return FunctionInfo(
                name=name,
                params=params,
                return_type=ret,
                docstring=None,
                docstring_full=None,
                calls=[],
                raises=[],
                decorators=[],
                complexity=1,
                lines=1,
                is_async=False,
                is_static=False,
                is_classmethod=False,
                is_property=False,
                intent=self.intent_gen.generate(name),
                start_line=0,
                end_line=0,
                is_private=not is_pub,
            )

        for m in re.finditer(r"^use\s+([^;]+);", content, re.MULTILINE):
            imports.append(m.group(1).strip())

        for m in re.finditer(r"^(?:pub\s+)?struct\s+(\w+)", content, re.MULTILINE):
            name = m.group(1)
            _get_or_create_class(name)
            types.append(TypeInfo(name=name, kind="struct", definition=""))
            exports.append(name)

        for m in re.finditer(r"^(?:pub\s+)?enum\s+(\w+)", content, re.MULTILINE):
            name = m.group(1)
            types.append(TypeInfo(name=name, kind="enum", definition=""))
            exports.append(name)

        for m in re.finditer(r"^(?:pub\s+)?trait\s+(\w+)", content, re.MULTILINE):
            name = m.group(1)
            types.append(TypeInfo(name=name, kind="trait", definition=""))
            exports.append(name)

        for m in re.finditer(r"^(?:pub\s+)?type\s+(\w+)\s*=", content, re.MULTILINE):
            name = m.group(1)
            types.append(TypeInfo(name=name, kind="type", definition=""))
            exports.append(name)

        for m in re.finditer(r"^(?:pub\s+)?mod\s+(\w+)\s*;", content, re.MULTILINE):
            name = m.group(1)
            types.append(TypeInfo(name=name, kind="module", definition=""))
            exports.append(name)

        fn_pat = re.compile(
            r"^\s*(?P<sig>(?:pub(?:\([^)]*\))?\s+)?fn)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?:->\s*(?P<ret>[^\s{]+))?",
            re.MULTILINE,
        )

        for m in fn_pat.finditer(content):
            functions.append(_parse_rust_fn(m, is_method=False))
            exports.append(m.group("name"))

        impl_pat = re.compile(
            r"^impl\b[^\{]*\{",
            re.MULTILINE,
        )

        for m in impl_pat.finditer(content):
            hdr = content[m.start() : m.end()]
            type_name = ""
            m_for = re.search(r"\bfor\s+(\w+)\b", hdr)
            if m_for:
                type_name = m_for.group(1)
            else:
                m_type = re.search(r"^impl\b[^\{]*?\b(\w+)\b\s*\{", hdr)
                if m_type:
                    type_name = m_type.group(1)

            if not type_name:
                continue

            open_idx = content.find("{", m.start(), m.end())
            if open_idx < 0:
                continue
            close_idx = _find_matching_brace(content, open_idx)
            if close_idx < 0:
                continue

            body = content[open_idx + 1 : close_idx]
            cls = _get_or_create_class(type_name)
            for fm in fn_pat.finditer(body):
                cls.methods.append(_parse_rust_fn(fm, is_method=True))

            exports.append(type_name)

        for m in re.finditer(
            r"^(?:pub\s+)?const\s+([A-Z][A-Z0-9_]*)\b", content, re.MULTILINE
        ):
            constants.append(m.group(1))

        for m in re.finditer(
            r"^(?:pub\s+)?static\s+(?:mut\s+)?([A-Z][A-Z0-9_]*)\b",
            content,
            re.MULTILINE,
        ):
            constants.append(m.group(1))

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language="rust",
            imports=imports[:PORT_20],
            exports=list(dict.fromkeys(exports))[:CONSTANT_50],
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("//")]
            ),
        )

    def _parse_java(self, filepath: str, content: str) -> ModuleInfo:
        """Parse Java using regex patterns."""
        imports: List[str] = []
        classes: List[ClassInfo] = []
        functions: List[FunctionInfo] = []
        types: List[TypeInfo] = []
        constants: List[str] = []
        exports: List[str] = []

        for m in re.finditer(r"^import\s+([^;]+);", content, re.MULTILINE):
            imports.append(m.group(1).strip())

        for m in re.finditer(
            r"^\s*(?:public\s+)?(?:abstract\s+)?class\s+(\w+)", content, re.MULTILINE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name, is_abstract="abstract" in m.group(0)))
            exports.append(name)

        for m in re.finditer(
            r"^\s*(?:public\s+)?interface\s+(\w+)", content, re.MULTILINE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name, is_interface=True))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="interface", definition=""))

        for m in re.finditer(r"^\s*(?:public\s+)?enum\s+(\w+)", content, re.MULTILINE):
            name = m.group(1)
            types.append(TypeInfo(name=name, kind="enum", definition=""))
            exports.append(name)

        for m in re.finditer(
            r"^\s*(?:public\s+)?record\s+(\w+)\s*\(", content, re.MULTILINE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name))
            types.append(TypeInfo(name=name, kind="record", definition=""))
            exports.append(name)

        # Method detection – allow indented declarations inside classes
        for m in re.finditer(
            r"^\s*(?:@\w+\s+)*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?([\w<>\[\],\s]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
            content,
            re.MULTILINE,
        ):
            ret_type = m.group(1)
            name = m.group(2)
            params = [
                p.strip() for p in (m.group(CONSTANT_3) or "").split(",") if p.strip()
            ][:CONSTANT_8]
            functions.append(
                FunctionInfo(
                    name=name,
                    params=params,
                    return_type=ret_type,
                    docstring=None,
                    docstring_full=None,
                    calls=[],
                    raises=[],
                    decorators=[],
                    complexity=1,
                    lines=1,
                    is_async=False,
                    is_static="static" in m.group(0),
                    is_classmethod=False,
                    is_property=False,
                    intent=self.intent_gen.generate(name),
                    start_line=0,
                    end_line=0,
                    is_private=False,
                )
            )

        for m in re.finditer(
            r"^\s*(?:public\s+)?static\s+final\s+[\w<>\[\]]+\s+([A-Z][A-Z0-9_]*)\b",
            content,
            re.MULTILINE,
        ):
            constants.append(m.group(1))

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language="java",
            imports=imports[:PORT_20],
            exports=list(dict.fromkeys(exports))[:CONSTANT_50],
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("//")]
            ),
        )

    def _parse_csharp(self, filepath: str, content: str) -> ModuleInfo:
        """Parse C# using regex patterns."""
        imports: List[str] = []
        classes: List[ClassInfo] = []
        functions: List[FunctionInfo] = []
        types: List[TypeInfo] = []
        constants: List[str] = []
        exports: List[str] = []

        for m in re.finditer(r"^using\s+([^;]+);", content, re.MULTILINE):
            imports.append(m.group(1).strip())

        for m in re.finditer(
            r"^\s*(?:public\s+)?interface\s+(I\w+)", content, re.MULTILINE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name, is_interface=True))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="interface", definition=""))

        for m in re.finditer(
            r"^\s*(?:public\s+)?(?:abstract\s+)?class\s+(\w+)", content, re.MULTILINE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name, is_abstract="abstract" in m.group(0)))
            exports.append(name)

        for m in re.finditer(
            r"^\s*(?:public\s+)?record\s+(\w+)", content, re.MULTILINE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="record", definition=""))

        for m in re.finditer(
            r"^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?(?:override\s+)?(?:virtual\s+)?([\w<>\[\]?]+)\s+(\w+)\s*\(([^)]*)\)\s*\{",
            content,
            re.MULTILINE,
        ):
            ret_type = m.group(1)
            name = m.group(2)
            params = [
                p.strip() for p in (m.group(CONSTANT_3) or "").split(",") if p.strip()
            ][:CONSTANT_8]
            functions.append(
                FunctionInfo(
                    name=name,
                    params=params,
                    return_type=ret_type,
                    docstring=None,
                    docstring_full=None,
                    calls=[],
                    raises=[],
                    decorators=[],
                    complexity=1,
                    lines=1,
                    is_async="async" in m.group(0),
                    is_static="static" in m.group(0),
                    is_classmethod=False,
                    is_property=False,
                    intent=self.intent_gen.generate(name),
                    start_line=0,
                    end_line=0,
                    is_private=False,
                )
            )

        for m in re.finditer(
            r"^\s*(?:public\s+)?const\s+[\w<>\[\]]+\s+([A-Z][A-Z0-9_]*)\b",
            content,
            re.MULTILINE,
        ):
            constants.append(m.group(1))

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language="csharp",
            imports=imports[:PORT_20],
            exports=list(dict.fromkeys(exports))[:CONSTANT_50],
            classes=classes,
            functions=functions,
            types=types,
            constants=constants[:10],
            docstring=None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("//")]
            ),
        )

    def _parse_sql(self, filepath: str, content: str) -> ModuleInfo:
        """Parse SQL using regex patterns."""
        imports: List[str] = []
        classes: List[ClassInfo] = []
        functions: List[FunctionInfo] = []
        types: List[TypeInfo] = []
        constants: List[str] = []
        exports: List[str] = []

        for m in re.finditer(r"CREATE\s+TABLE\s+(\w+)", content, re.IGNORECASE):
            name = m.group(1)
            classes.append(ClassInfo(name=name))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="table", definition=""))

        for m in re.finditer(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)", content, re.IGNORECASE
        ):
            name = m.group(1)
            classes.append(ClassInfo(name=name))
            exports.append(name)
            types.append(TypeInfo(name=name, kind="view", definition=""))

        for m in re.finditer(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)", content, re.IGNORECASE
        ):
            name = m.group(1)
            functions.append(
                FunctionInfo(
                    name=name,
                    params=[],
                    return_type="",
                    docstring=None,
                    docstring_full=None,
                    calls=[],
                    raises=[],
                    decorators=[],
                    complexity=1,
                    lines=1,
                    is_async=False,
                    is_static=False,
                    is_classmethod=False,
                    is_property=False,
                    intent=self.intent_gen.generate(name),
                    start_line=0,
                    end_line=0,
                    is_private=False,
                )
            )
            exports.append(name)

        lines = content.split("\n")
        return ModuleInfo(
            path=filepath,
            language="sql",
            imports=imports,
            exports=list(dict.fromkeys(exports))[:CONSTANT_50],
            classes=classes,
            functions=functions,
            types=types,
            constants=constants,
            docstring=None,
            lines_total=len(lines),
            lines_code=len(
                [l for l in lines if l.strip() and not l.strip().startswith("--")]
            ),
        )


def is_tree_sitter_available() -> bool:
    """Check if Tree-sitter is available."""
    return TREE_SITTER_AVAILABLE
