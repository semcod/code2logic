"""
Tests for shared_utils module.

Tests common utility functions used across Code2Logic generators.
"""

from code2logic.shared_utils import (
    compact_imports,
    deduplicate_imports,
    abbreviate_type,
    expand_type,
    build_signature,
    remove_self_from_params,
    categorize_function,
    extract_domain,
    compute_hash,
    truncate_docstring,
    escape_for_yaml,
    clean_identifier,
)


class TestCompactImports:
    """Tests for compact_imports function."""

    def test_groups_submodules(self):
        """Verify submodules are grouped with curly braces."""
        imports = ["typing.Dict", "typing.List", "typing.Optional"]
        result = compact_imports(imports)
        # Should have grouped format
        assert any("{" in r for r in result)
        assert len(result) < len(imports)

    def test_preserves_standalone(self):
        """Verify standalone imports are preserved."""
        imports = ["json", "os", "re"]
        result = compact_imports(imports)
        assert set(result) == set(imports)

    def test_limits_output(self):
        """Verify output is limited to max_items."""
        imports = [f"module{i}" for i in range(20)]
        result = compact_imports(imports, max_items=5)
        assert len(result) <= 5

    def test_handles_empty(self):
        """Verify empty input returns empty list."""
        assert compact_imports([]) == []

    def test_skips_module_module_duplicates(self):
        """Verify module.module duplicates are handled."""
        imports = ["dataclasses", "dataclasses.dataclass"]
        result = compact_imports(imports)
        # Should not have duplicated base names
        assert "dataclasses.dataclasses" not in str(result)


class TestDeduplicateImports:
    """Tests for deduplicate_imports function."""

    def test_removes_base_when_specific_exists(self):
        """Verify base is removed when more specific import exists."""
        imports = ["typing", "typing.Dict"]
        result = deduplicate_imports(imports)
        assert "typing.Dict" in result
        # typing alone should be excluded if typing.Dict exists
        base_only = [i for i in result if i == "typing"]
        assert len(base_only) == 0

    def test_handles_empty(self):
        """Verify empty input returns empty list."""
        assert deduplicate_imports([]) == []


class TestAbbreviateType:
    """Tests for abbreviate_type function."""

    def test_simple_types(self):
        """Verify simple types are abbreviated."""
        assert abbreviate_type("str") == "s"
        assert abbreviate_type("int") == "i"
        assert abbreviate_type("bool") == "b"
        assert abbreviate_type("None") == "N"

    def test_complex_types(self):
        """Verify complex types are abbreviated."""
        assert abbreviate_type("Dict[str, Any]") == "D[s,A]"
        assert abbreviate_type("List[str]") == "L[s]"

    def test_optional_type(self):
        """Verify Optional is abbreviated to ?."""
        result = abbreviate_type("Optional[str]")
        assert "?" in result
        assert "s" in result

    def test_preserves_unknown(self):
        """Verify unknown types are preserved."""
        assert abbreviate_type("CustomType") == "CustomType"

    def test_handles_empty(self):
        """Verify empty input returns empty string."""
        assert abbreviate_type("") == ""
        assert abbreviate_type(None) == ""


class TestExpandType:
    """Tests for expand_type function."""

    def test_expands_abbreviated(self):
        """Verify abbreviated types are expanded."""
        assert "str" in expand_type("s")
        assert "Dict" in expand_type("D")

    def test_handles_empty(self):
        """Verify empty input returns empty string."""
        assert expand_type("") == ""


class TestBuildSignature:
    """Tests for build_signature function."""

    def test_removes_self_by_default(self):
        """Verify self is removed by default."""
        sig = build_signature(["self", "name", "value"], "None")
        assert "self" not in sig
        assert "name" in sig

    def test_includes_self_when_requested(self):
        """Verify self is included when requested."""
        sig = build_signature(["self", "name"], "None", include_self=True)
        assert "self" in sig

    def test_removes_cls(self):
        """Verify cls is also removed."""
        sig = build_signature(["cls", "name"], "MyClass")
        assert "cls" not in sig
        assert "name" in sig

    def test_abbreviates_types(self):
        """Verify types are abbreviated when requested."""
        sig = build_signature(
            ["name:str", "count:int"], "Dict[str, Any]", abbreviate=True
        )
        assert ":s" in sig
        assert "D[" in sig

    def test_truncates_params(self):
        """Verify excess params are truncated with indicator."""
        params = [f"param{i}:str" for i in range(10)]
        sig = build_signature(params, max_params=3)
        assert "..." in sig

    def test_includes_return_type(self):
        """Verify return type is included."""
        sig = build_signature(["x"], "int")
        assert "->int" in sig

    def test_no_return_type(self):
        """Verify no arrow when no return type."""
        sig = build_signature(["x"])
        assert "->" not in sig


class TestRemoveSelfFromParams:
    """Tests for remove_self_from_params function."""

    def test_removes_self(self):
        """Verify self is removed."""
        result = remove_self_from_params(["self", "name", "value"])
        assert "self" not in result
        assert "name" in result

    def test_removes_cls(self):
        """Verify cls is removed."""
        result = remove_self_from_params(["cls", "name"])
        assert "cls" not in result

    def test_removes_typed_self(self):
        """Verify self with type annotation is removed."""
        result = remove_self_from_params(["self: MyClass", "name"])
        assert len(result) == 1
        assert "name" in result


class TestCategorizeFunction:
    """Tests for categorize_function function."""

    def test_read_category(self):
        """Verify read-related functions are categorized."""
        assert categorize_function("get_user") == "read"
        assert categorize_function("fetch_data") == "read"
        assert categorize_function("find_by_id") == "read"
        assert categorize_function("load_config") == "read"

    def test_create_category(self):
        """Verify create-related functions are categorized."""
        assert categorize_function("create_user") == "create"
        assert categorize_function("add_item") == "create"
        assert categorize_function("make_request") == "create"

    def test_update_category(self):
        """Verify update-related functions are categorized."""
        assert categorize_function("update_user") == "update"
        assert categorize_function("set_value") == "update"

    def test_delete_category(self):
        """Verify delete-related functions are categorized."""
        assert categorize_function("delete_user") == "delete"
        assert categorize_function("remove_item") == "delete"

    def test_handles_method_names(self):
        """Verify class.method names are handled."""
        assert categorize_function("User.get_name") == "read"

    def test_returns_other_for_unknown(self):
        """Verify unknown patterns return 'other'."""
        assert categorize_function("foo") == "other"
        assert categorize_function("xyz") == "other"


class TestExtractDomain:
    """Tests for extract_domain function."""

    def test_extracts_known_domain(self):
        """Verify known domains are extracted."""
        assert extract_domain("src/auth/login.py") == "auth"
        assert extract_domain("lib/user_service.py") == "user"

    def test_handles_windows_paths(self):
        """Verify Windows-style paths are handled."""
        assert extract_domain("src\\config\\settings.py") == "config"

    def test_returns_parent_for_unknown(self):
        """Verify parent folder is returned for unknown domains."""
        result = extract_domain("foo/bar/baz.py")
        assert result in ("bar", "root")


class TestComputeHash:
    """Tests for compute_hash function."""

    def test_returns_hex_string(self):
        """Verify hash is a hex string."""
        h = compute_hash("function", "(a,b)->int")
        assert all(c in "0123456789abcdef" for c in h)

    def test_respects_length(self):
        """Verify hash length is respected."""
        h = compute_hash("func", "sig", length=12)
        assert len(h) == 12

    def test_same_input_same_hash(self):
        """Verify same input produces same hash."""
        h1 = compute_hash("func", "(a)->b")
        h2 = compute_hash("func", "(a)->b")
        assert h1 == h2

    def test_different_input_different_hash(self):
        """Verify different input produces different hash."""
        h1 = compute_hash("func1", "(a)->b")
        h2 = compute_hash("func2", "(a)->b")
        assert h1 != h2


class TestTruncateDocstring:
    """Tests for truncate_docstring function."""

    def test_truncates_long(self):
        """Verify long docstrings are truncated."""
        doc = "This is a very long docstring " * 10
        result = truncate_docstring(doc, max_length=30)
        assert len(result) <= 33  # 30 + '...'

    def test_preserves_short(self):
        """Verify short docstrings are preserved."""
        doc = "Short doc"
        result = truncate_docstring(doc, max_length=60)
        assert result == "Short doc"

    def test_removes_markers(self):
        """Verify docstring markers are removed."""
        doc = '"""This is the doc"""'
        result = truncate_docstring(doc)
        assert '"""' not in result

    def test_stops_at_sentence_end(self):
        """Verify truncation stops at sentence end."""
        doc = "First sentence. Second sentence continues."
        result = truncate_docstring(doc, max_length=60)
        assert result == "First sentence."

    def test_handles_empty(self):
        """Verify empty input returns empty string."""
        assert truncate_docstring("") == ""
        assert truncate_docstring(None) == ""


class TestEscapeForYaml:
    """Tests for escape_for_yaml function."""

    def test_removes_newlines(self):
        """Verify newlines are removed."""
        result = escape_for_yaml("line1\nline2")
        assert "\n" not in result

    def test_quotes_special_chars(self):
        """Verify special characters cause quoting."""
        result = escape_for_yaml("value: with colon")
        assert result.startswith('"') or ":" in result

    def test_handles_empty(self):
        """Verify empty input returns empty string."""
        assert escape_for_yaml("") == ""


class TestCleanIdentifier:
    """Tests for clean_identifier function."""

    def test_removes_whitespace(self):
        """Verify whitespace is removed."""
        result = clean_identifier("  name\n  ")
        assert result == "name"

    def test_handles_empty(self):
        """Verify empty input returns empty string."""
        assert clean_identifier("") == ""
