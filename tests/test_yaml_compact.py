"""
Tests for compact YAML format generation.

Verifies:
- Short keys are used (p, l, i, e, c, f, n, d, m)
- 'self' is removed from method signatures
- Imports are deduplicated (typing.{Dict,List})
- Empty fields (bases:[], decorators:[]) are omitted
- Header comment with key legend is present
"""

import pytest
import yaml
from code2logic import analyze_project
from code2logic.generators import YAMLGenerator
from code2logic.models import ProjectInfo, ModuleInfo, ClassInfo, FunctionInfo


@pytest.fixture
def sample_project():
    """Create a sample project for testing."""
    func1 = FunctionInfo(
        name="get_profile",
        params=["self", "name:str", "verbose:bool"],
        return_type="Profile",
        docstring="Get a profile by name.",
        calls=[],
        raises=[],
        complexity=1,
        lines=10,
        decorators=[],
        is_async=False,
        is_static=False,
        is_private=False,
        intent="Get a profile by name.",
    )

    cls1 = ClassInfo(
        name="ProfileManager",
        bases=[],  # Empty - should be omitted
        docstring="Manages user profiles.",
        methods=[func1],
        properties=["name: str", "active: bool"],
        is_interface=False,
        is_abstract=False,
        generic_params=[],
    )

    module1 = ModuleInfo(
        path="profile_manager.py",
        language="python",
        imports=["typing.Dict", "typing.List", "typing.Optional", "json", "os"],
        exports=["ProfileManager", "get_profile"],
        classes=[cls1],
        functions=[],
        types=[],
        constants=[],
        docstring="Profile management module.",
        lines_total=100,
        lines_code=80,
    )

    return ProjectInfo(
        name="test_project",
        root_path="/test",
        languages={"python": 1},
        modules=[module1],
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=1,
        total_lines=100,
        generated_at="",
    )


class TestYAMLShortKeys:
    """Test that YAML uses short keys."""

    def test_short_keys_in_module(self, sample_project):
        """Verify modules use short keys."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")
        data = yaml.safe_load(yaml_str)

        mod = data["modules"][0]
        assert "p" in mod, "Should have 'p' (path)"
        assert "path" not in mod, "Should not have 'path'"
        assert "l" in mod, "Should have 'l' (lines)"
        assert "lines" not in mod, "Should not have 'lines'"
        assert "i" in mod, "Should have 'i' (imports)"
        assert "imports" not in mod, "Should not have 'imports'"

    def test_short_keys_in_class(self, sample_project):
        """Verify classes use short keys."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")
        data = yaml.safe_load(yaml_str)

        cls = data["modules"][0]["c"][0]
        assert "n" in cls, "Should have 'n' (name)"
        assert "name" not in cls, "Should not have 'name'"
        assert "d" in cls, "Should have 'd' (docstring)"
        assert "docstring" not in cls, "Should not have 'docstring'"


class TestSelfRemoval:
    """Test that 'self' is removed from method signatures."""

    def test_no_self_in_signature(self, sample_project):
        """Verify 'self' is not in method signatures."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="full")
        data = yaml.safe_load(yaml_str)

        # Check method signatures don't contain 'self'
        for mod in data["modules"]:
            for cls in mod.get("c", []):
                for method in cls.get("m", []):
                    sig = method.get("sig", "")
                    assert "self" not in sig, (
                        f"Signature should not contain 'self': {sig}"
                    )


class TestImportDeduplication:
    """Test that imports are deduplicated."""

    def test_typing_grouped(self, sample_project):
        """Verify typing imports are grouped."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")
        data = yaml.safe_load(yaml_str)

        imports = data["modules"][0]["i"]
        # Should have grouped typing imports
        typing_entries = [i for i in imports if i.startswith("typing")]
        assert len(typing_entries) == 1, (
            f"Should have one grouped typing entry, got: {typing_entries}"
        )
        # Should contain the grouped format
        assert any("{" in i for i in typing_entries), (
            "Should use grouped format like typing.{Dict,List}"
        )


class TestEmptyFieldsOmitted:
    """Test that empty fields are omitted."""

    def test_empty_bases_omitted(self, sample_project):
        """Verify empty bases are not included."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")

        assert "bases: []" not in yaml_str
        assert "b: []" not in yaml_str

    def test_empty_decorators_omitted(self, sample_project):
        """Verify empty decorators are not included."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="full")

        assert "decorators: []" not in yaml_str
        assert "decorators: -" not in yaml_str


class TestMetaLegend:
    """Test that meta.legend provides key transparency."""

    def test_meta_legend_structure(self, sample_project):
        """Verify meta.legend contains all expected key mappings."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")
        data = yaml.safe_load(yaml_str)

        # Should have meta.legend structure
        assert "meta" in data
        assert "legend" in data["meta"]
        legend = data["meta"]["legend"]

        # Check required legend mappings
        required_mappings = {
            "p": "path",
            "l": "lines",
            "i": "imports",
            "e": "exports",
            "c": "classes",
            "f": "functions",
            "n": "name",
            "d": "docstring",
            "b": "bases",
            "m": "methods",
        }

        for short, full in required_mappings.items():
            assert short in legend, f"Legend missing '{short}' key"
            assert legend[short] == full, (
                f"Legend '{short}' should map to '{full}', got '{legend[short]}'"
            )

    def test_meta_legend_in_output(self, sample_project):
        """Verify meta.legend appears in YAML output string."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")

        # Should contain meta.legend structure in output
        assert "meta:" in yaml_str
        assert "legend:" in yaml_str
        assert "p: path" in yaml_str
        assert "l: lines" in yaml_str
        assert "n: name" in yaml_str


class TestCompactSizeReduction:
    """Test that compact format reduces output size for larger projects."""

    def test_compact_smaller_for_large_projects(self):
        """Verify compact format is smaller for real projects (header overhead amortized)."""
        import os

        # Use actual codebase for realistic test
        if os.path.exists("code2logic"):
            p = analyze_project("code2logic/", use_treesitter=False)
            gen = YAMLGenerator()
            compact = gen.generate(p, compact=True, detail="standard")
            full = gen.generate(p, compact=False, detail="standard")

            # For larger projects, compact should be smaller
            # (header overhead is amortized across many modules)
            assert len(compact) < len(full), (
                f"Compact ({len(compact)}) should be smaller than full ({len(full)})"
            )
        else:
            pytest.skip("code2logic directory not found")


class TestDocstringTruncation:
    """Test that docstrings are truncated."""

    def test_class_docstring_truncated(self, sample_project):
        """Verify class docstrings are truncated to 60 chars."""
        gen = YAMLGenerator()
        yaml_str = gen.generate(sample_project, compact=True, detail="standard")
        data = yaml.safe_load(yaml_str)

        cls = data["modules"][0]["c"][0]
        if "d" in cls:
            assert len(cls["d"]) <= 65, "Docstring should be truncated"
