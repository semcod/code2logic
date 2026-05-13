"""Tests for output generators."""

import json
import pytest

from code2logic import (
    MarkdownGenerator,
    CompactGenerator,
    JSONGenerator,
    ProjectInfo,
    ModuleInfo,
    ClassInfo,
    FunctionInfo,
)


@pytest.fixture
def sample_project():
    """Create a sample project for testing generators."""
    func1 = FunctionInfo(
        name="hello",
        params=["name:str"],
        return_type="str",
        docstring="Say hello",
        calls=["print"],
        raises=[],
        complexity=1,
        lines=3,
        decorators=[],
        is_async=False,
        is_static=False,
        is_private=False,
        intent="greets someone",
        start_line=1,
        end_line=3,
    )

    method1 = FunctionInfo(
        name="greet",
        params=["self", "name:str"],
        return_type="str",
        docstring="Greet method",
        calls=[],
        raises=[],
        complexity=1,
        lines=2,
        decorators=[],
        is_async=False,
        is_static=False,
        is_private=False,
        intent="greets",
        start_line=10,
        end_line=12,
    )

    class1 = ClassInfo(
        name="Greeter",
        bases=["BaseGreeter"],
        docstring="A greeter class",
        methods=[method1],
        properties=["prefix"],
        is_interface=False,
        is_abstract=False,
        generic_params=[],
    )

    module1 = ModuleInfo(
        path="main.py",
        language="python",
        imports=["os", "sys"],
        exports=["hello", "Greeter"],
        classes=[class1],
        functions=[func1],
        types=[],
        constants=["VERSION"],
        docstring="Main module",
        lines_total=50,
        lines_code=40,
    )

    module2 = ModuleInfo(
        path="utils/helpers.py",
        language="python",
        imports=["main"],
        exports=["format_name"],
        classes=[],
        functions=[],
        types=[],
        constants=[],
        docstring="Helpers",
        lines_total=20,
        lines_code=15,
    )

    return ProjectInfo(
        name="test_project",
        root_path="/test/project",
        languages={"python": 2},
        modules=[module1, module2],
        dependency_graph={"utils/helpers.py": ["main.py"]},
        dependency_metrics={},
        entrypoints=["main.py"],
        similar_functions={},
        total_files=2,
        total_lines=70,
        generated_at="2025-01-01T00:00:00",
    )


class TestMarkdownGenerator:
    """Tests for MarkdownGenerator."""

    def test_generate_basic(self, sample_project):
        """Test basic Markdown generation."""
        gen = MarkdownGenerator()
        output = gen.generate(sample_project)

        assert "# 📦 test_project" in output
        assert "files: 2" in output
        assert "lines: 70" in output

    def test_generate_includes_modules(self, sample_project):
        """Test that modules are included."""
        gen = MarkdownGenerator()
        output = gen.generate(sample_project)

        assert "main.py" in output
        assert "helpers.py" in output

    def test_generate_includes_classes(self, sample_project):
        """Test that classes are included."""
        gen = MarkdownGenerator()
        output = gen.generate(sample_project)

        assert "class `Greeter`" in output
        assert "BaseGreeter" in output

    def test_generate_includes_functions(self, sample_project):
        """Test that functions are included."""
        gen = MarkdownGenerator()
        output = gen.generate(sample_project)

        assert "hello" in output
        assert "greets" in output.lower()

    def test_generate_includes_entrypoints(self, sample_project):
        """Test that entrypoints are included."""
        gen = MarkdownGenerator()
        output = gen.generate(sample_project)

        assert "main.py" in output

    def test_detail_levels(self, sample_project):
        """Test different detail levels."""
        gen = MarkdownGenerator()

        compact = gen.generate(sample_project, "compact")
        standard = gen.generate(sample_project, "standard")
        detailed = gen.generate(sample_project, "detailed")

        # Detailed should be longest
        assert len(detailed) >= len(standard)
        assert len(standard) >= len(compact)


class TestCompactGenerator:
    """Tests for CompactGenerator."""

    def test_generate_basic(self, sample_project):
        """Test basic compact generation."""
        gen = CompactGenerator()
        output = gen.generate(sample_project)

        assert "test_project" in output
        assert "2f" in output  # 2 files
        assert "70L" in output  # 70 lines

    def test_generate_includes_hubs(self, sample_project):
        """Test that ENTRY is included."""
        gen = CompactGenerator()
        output = gen.generate(sample_project)

        assert "ENTRY:" in output
        assert "main.py" in output

    def test_compact_is_smaller(self, sample_project):
        """Test that compact output is smaller than markdown."""
        md_gen = MarkdownGenerator()
        compact_gen = CompactGenerator()

        md_output = md_gen.generate(sample_project)
        compact_output = compact_gen.generate(sample_project)

        assert len(compact_output) < len(md_output)


class TestJSONGenerator:
    """Tests for JSONGenerator."""

    def test_generate_valid_json(self, sample_project):
        """Test that output is valid JSON."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        data = json.loads(output)
        assert data is not None

    def test_generate_structure(self, sample_project):
        """Test JSON structure."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        data = json.loads(output)

        assert data["name"] == "test_project"
        assert data["statistics"]["files"] == 2
        assert data["statistics"]["lines"] == 70
        assert len(data["modules"]) == 2

    def test_generate_modules(self, sample_project):
        """Test module structure in JSON."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        data = json.loads(output)

        main_module = next(m for m in data["modules"] if m["path"] == "main.py")

        assert main_module["language"] == "python"
        assert "hello" in main_module["exports"]
        assert len(main_module["classes"]) == 1
        assert len(main_module["functions"]) == 1

    def test_generate_functions(self, sample_project):
        """Test function structure in JSON."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        data = json.loads(output)

        main_module = next(m for m in data["modules"] if m["path"] == "main.py")
        hello_func = main_module["functions"][0]

        assert hello_func["name"] == "hello"
        assert "signature" in hello_func
        assert hello_func["intent"] == "greets someone"

    def test_generate_classes(self, sample_project):
        """Test class structure in JSON."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        data = json.loads(output)

        main_module = next(m for m in data["modules"] if m["path"] == "main.py")
        greeter_class = main_module["classes"][0]

        assert greeter_class["name"] == "Greeter"
        assert "BaseGreeter" in greeter_class["bases"]
        assert len(greeter_class["methods"]) == 1
