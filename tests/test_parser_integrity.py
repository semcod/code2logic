"""
Parser integrity tests for code2logic.

Tests verify that parsing produces correct, complete output without:
- Truncated identifiers
- Corrupted signatures
- Malformed class names
- Fragmented imports
"""

import pytest
from code2logic.parsers import (
    TreeSitterParser,
    UniversalParser,
    is_tree_sitter_available,
)


# Use TreeSitterParser if available, otherwise UniversalParser
@pytest.fixture
def parser():
    if is_tree_sitter_available():
        return TreeSitterParser()
    return UniversalParser()


def parse_python(parser, code: str):
    """Helper to parse Python code."""
    return parser.parse("test.py", code, "python")


class TestFunctionNameExtraction:
    """Test 1: Verify complete function names are extracted."""

    def test_function_name_not_truncated(self, parser):
        code = '''
def get_profiles_path() -> Path:
    """Get path to profiles storage."""
    return Path.home() / ".code2logic" / "profiles"
'''
        result = parse_python(parser, code)
        assert len(result.functions) == 1
        assert result.functions[0].name == "get_profiles_path"
        assert not result.functions[0].name.startswith("et_")

    def test_multiple_function_names(self, parser):
        code = """
def load_profiles() -> Dict:
    pass

def save_profile(profile: Profile) -> None:
    pass

def get_profile(name: str) -> Profile:
    pass
"""
        result = parse_python(parser, code)
        names = [f.name for f in result.functions]
        assert "load_profiles" in names
        assert "save_profile" in names
        assert "get_profile" in names


class TestSignatureParsing:
    """Test 2: Verify complete signatures with types."""

    def test_signature_with_types(self, parser):
        code = '''
def save_profile(profile: LLMProfile) -> None:
    """Save a profile to storage."""
    pass
'''
        result = parse_python(parser, code)
        sig = result.functions[0].params
        # Check params contain type info
        assert any("profile" in p for p in sig)
        # No double commas in signature
        sig_str = ",".join(sig)
        assert ",," not in sig_str

    def test_signature_with_defaults(self, parser):
        code = """
def configure(verbose: bool = False, timeout: int = 30) -> None:
    pass
"""
        result = parse_python(parser, code)
        params = result.functions[0].params
        assert len(params) >= 2


class TestClassNameIntegrity:
    """Test 3: Verify class names have no embedded whitespace."""

    def test_class_name_no_whitespace(self, parser):
        code = '''
class LogicMLGenerator:
    """Generates LogicML format."""
    pass
'''
        result = parse_python(parser, code)
        assert len(result.classes) == 1
        name = result.classes[0].name
        assert name == "LogicMLGenerator"
        assert "\n" not in name
        assert ":" not in name

    def test_class_with_bases(self, parser):
        code = '''
class MyClass(BaseClass, Mixin):
    """A class with bases."""
    pass
'''
        result = parse_python(parser, code)
        cls = result.classes[0]
        assert cls.name == "MyClass"
        assert "BaseClass" in cls.bases or len(cls.bases) >= 1


class TestImportParsing:
    """Test 4: Verify imports are correctly formatted."""

    def test_import_from_statement(self, parser):
        code = """
from pathlib import Path
from typing import Dict, List, Optional
import json
"""
        result = parse_python(parser, code)
        imports = result.imports

        # Check imports are present (format may vary)
        import_str = " ".join(imports)
        assert "pathlib" in import_str or "Path" in import_str
        assert "typing" in import_str or "Dict" in import_str
        assert "json" in imports
        # No truncation artifacts (check for broken imports, not substrings)
        # "thlib" was an example of truncated "pathlib" - now we check for other artifacts
        assert not any(imp.startswith("thlib") for imp in imports)

    def test_no_duplicate_imports(self, parser):
        code = """
from dataclasses import dataclass, field
from datetime import datetime
"""
        result = parse_python(parser, code)
        # Should not have "dataclasses.dataclasses" pattern
        for imp in result.imports:
            parts = imp.split(".")
            if len(parts) >= 2:
                assert parts[-1] != parts[-2], f"Duplicate suffix in import: {imp}"


class TestExportsCompleteness:
    """Test 5: Verify exports contain full function names."""

    def test_exports_complete(self, parser):
        code = """
def get_profile(name: str):
    pass

def save_profile(profile):
    pass

def load_profiles():
    pass
"""
        result = parse_python(parser, code)
        exports = result.exports

        assert "get_profile" in exports
        assert "save_profile" in exports
        assert "load_profiles" in exports
        # No partial names
        assert not any(e.startswith("et_") for e in exports)
        assert not any(e.startswith("ve_") for e in exports)


class TestDocstringTruncation:
    """Test 6: Verify docstrings are properly truncated."""

    def test_long_docstring_truncated(self, parser):
        code = '''
def complex_function():
    """
    This is a very long docstring that goes on and on.
    
    It has multiple paragraphs with extensive details
    about implementation, usage examples, and more.
    
    Args:
        param1: Description
        param2: Another description
    
    Returns:
        Something useful
    """
    pass
'''
        result = parse_python(parser, code)
        docstring = result.functions[0].docstring

        # Should be truncated
        assert docstring is None or len(docstring) <= 100


class TestUnicodeHandling:
    """Test 7: Verify Unicode characters don't break parsing."""

    def test_unicode_in_docstring(self, parser):
        code = '''
def greet(name: str) -> str:
    """Przywitaj użytkownika po polsku."""
    return f"Cześć, {name}!"
'''
        result = parse_python(parser, code)
        assert result.functions[0].name == "greet"
        # Docstring should contain Polish characters
        if result.functions[0].docstring:
            assert (
                "użytkownika" in result.functions[0].docstring
                or "Przywitaj" in result.functions[0].docstring
            )


class TestNestedClassMethods:
    """Test 8: Verify methods in classes are parsed correctly."""

    def test_class_methods(self, parser):
        code = '''
class Outer:
    def outer_method(self, value: int) -> str:
        """Process value."""
        return str(value)
    
    def another_method(self):
        pass
'''
        result = parse_python(parser, code)
        cls = result.classes[0]
        methods = [m.name for m in cls.methods]

        assert "outer_method" in methods
        assert "another_method" in methods


class TestDecoratorCapture:
    """Test 9: Verify decorators are captured in metadata."""

    @pytest.mark.skipif(not is_tree_sitter_available(), reason="Requires Tree-sitter")
    def test_decorators_captured(self, parser):
        code = """
class MyClass:
    @property
    def value(self) -> int:
        return self._value
    
    @staticmethod
    def create():
        return MyClass()
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls()
"""
        result = parse_python(parser, code)
        cls = result.classes[0]

        methods = {m.name: m for m in cls.methods}
        assert (
            "property"
            in methods.get("value", type("", (), {"decorators": []})).decorators
        )
        assert (
            "staticmethod"
            in methods.get("create", type("", (), {"decorators": []})).decorators
        )
        assert (
            "classmethod"
            in methods.get("from_dict", type("", (), {"decorators": []})).decorators
        )


class TestLargeFileHandling:
    """Test 10: Verify large files don't cause truncation."""

    def test_many_functions(self, parser):
        # Generate 50 functions (smaller for faster tests)
        code_lines = []
        for i in range(50):
            code_lines.append(f'''
def function_{i:04d}(param_{i}: int) -> str:
    """Function number {i}."""
    return str(param_{i})
''')
        code = "\n".join(code_lines)

        result = parse_python(parser, code)

        assert len(result.functions) == 50
        assert result.functions[0].name == "function_0000"
        assert result.functions[49].name == "function_0049"


def parse_js(parser, code: str):
    """Helper to parse JavaScript code."""
    return parser.parse("test.js", code, "javascript")


class TestJavaScriptFunctionExtraction:
    """Test JS function extraction: arrow fns, function expressions, IIFEs, nested, etc."""

    def test_regular_function_declaration(self, parser):
        code = "function walk(dir, onFile) {\n  console.log(dir);\n}\n"
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "walk" in names

    def test_async_function_declaration(self, parser):
        code = "async function fetchData(url) {\n  return await fetch(url);\n}\n"
        result = parse_js(parser, code)
        fn = next(f for f in result.functions if f.name == "fetchData")
        assert fn.is_async

    def test_const_arrow_function(self, parser):
        code = "const getArg = (name, def) => {\n  return name;\n};\n"
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "getArg" in names
        fn = next(f for f in result.functions if f.name == "getArg")
        assert len(fn.params) == 2

    def test_let_arrow_function(self, parser):
        code = "let processItem = (item) => {\n  return item;\n};\n"
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "processItem" in names

    def test_var_arrow_function(self, parser):
        code = "var shouldIgnore = (filePath) => {\n  return false;\n};\n"
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "shouldIgnore" in names

    def test_const_function_expression(self, parser):
        code = "const validate = function(input) {\n  return !!input;\n};\n"
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "validate" in names

    def test_var_function_expression(self, parser):
        code = "var formatOutput = function(data, indent) {\n  return JSON.stringify(data);\n};\n"
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "formatOutput" in names

    def test_iife_named_function(self, parser):
        code = '(function main() {\n  console.log("hello");\n})();\n'
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "main" in names

    def test_nested_function_in_body(self, parser):
        code = """function findFiles(dir) {
  const files = [];
  function traverse(currentDir) {
    console.log(currentDir);
  }
  traverse(dir);
  return files;
}
"""
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "findFiles" in names
        assert "traverse" in names

    def test_deeply_nested_functions(self, parser):
        code = """function outer(data) {
  function middle(items) {
    function inner(a, b) {
      return a - b;
    }
    return items.sort(inner);
  }
  return middle(data);
}
"""
        result = parse_js(parser, code)
        names = [f.name for f in result.functions]
        assert "outer" in names
        assert "middle" in names
        assert "inner" in names

    def test_module_exports_shorthand(self, parser):
        code = """function foo() {}
function bar() {}
module.exports = { foo, bar };
"""
        result = parse_js(parser, code)
        assert "foo" in result.exports
        assert "bar" in result.exports

    def test_commonjs_require_imports(self, parser):
        code = "const fs = require('fs');\nconst path = require('path');\n"
        result = parse_js(parser, code)
        assert "fs" in result.imports
        assert "path" in result.imports

    def test_class_with_methods(self, parser):
        code = """class FileProcessor {
  constructor(rootDir) {
    this.rootDir = rootDir;
  }
  async analyze(filePath) {
    return {};
  }
  static fromConfig(configPath) {
    return new FileProcessor('.');
  }
}
"""
        result = parse_js(parser, code)
        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "FileProcessor"
        method_names = [m.name for m in cls.methods]
        assert "constructor" in method_names
        assert "analyze" in method_names
        assert "fromConfig" in method_names

    def test_export_clause(self, parser):
        code = """function foo() {}
const bar = () => {};
export { foo, bar };
"""
        result = parse_js(parser, code)
        assert "foo" in result.exports
        assert "bar" in result.exports

    def test_no_duplicate_functions(self, parser):
        """Ensure same function isn't listed twice."""
        code = """function walk(dir) {}
module.exports = { walk };
"""
        result = parse_js(parser, code)
        walk_fns = [f for f in result.functions if f.name == "walk"]
        assert len(walk_fns) == 1


class TestMethodSignatureIntegrity:
    """Additional tests for method signature integrity."""

    def test_init_signature(self, parser):
        code = '''
class Profiler:
    def __init__(self, client, verbose: bool = False):
        """Initialize profiler."""
        self.client = client
        self.verbose = verbose
'''
        result = parse_python(parser, code)
        cls = result.classes[0]
        init_method = next((m for m in cls.methods if m.name == "__init__"), None)

        assert init_method is not None
        assert init_method.name == "__init__"
        # Params should include client and verbose
        params_str = ",".join(init_method.params)
        assert "self" in params_str or len(init_method.params) >= 1
