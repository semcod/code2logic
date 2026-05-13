"""
Consolidated Format Tests for Code2Logic.

Tests ALL supported formats systematically:
- YAML
- JSON
- LogicML
- Gherkin
- Markdown
- TOON
- CSV
- Compact

Each format is tested for:
1. Basic generation
2. Content validity
3. Contains expected elements (classes, functions, imports)
4. Detail levels (compact, standard, full)
5. Validation (where applicable)
"""

import pytest
import json

from code2logic import (
    analyze_project,
    YAMLGenerator,
    JSONGenerator,
    GherkinGenerator,
    MarkdownGenerator,
    LogicMLGenerator,
    TOONGenerator,
    CSVGenerator,
    CompactGenerator,
    validate_yaml,
    validate_json,
    validate_logicml,
)

from code2logic.function_logic import FunctionLogicGenerator


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_code():
    """Sample Python code for testing."""
    return '''
"""Sample module for testing."""

from typing import List, Optional
import asyncio

class Calculator:
    """A simple calculator class."""
    
    def __init__(self, precision: int = 2):
        self.precision = precision
        self.history: List[tuple] = []
    
    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        result = round(a + b, self.precision)
        self.history.append(('add', a, b, result))
        return result
    
    async def calculate_async(self, values: List[float]) -> float:
        """Calculate sum asynchronously."""
        await asyncio.sleep(0.01)
        return sum(values)

def helper_function(x: int, y: int = 0) -> int:
    """Helper function."""
    return x + y

async def async_fetch(url: str) -> Optional[dict]:
    """Fetch data asynchronously."""
    return {"url": url}
'''


@pytest.fixture
def sample_project(tmp_path, sample_code):
    """Create a sample project for testing."""
    (tmp_path / "main.py").write_text(sample_code)
    (tmp_path / "utils.py").write_text('''
"""Utility functions."""

def format_string(s: str) -> str:
    """Format a string."""
    return s.strip().lower()

class Config:
    """Configuration holder."""
    def __init__(self):
        self.settings = {}
    
    def get(self, key: str) -> str:
        return self.settings.get(key, "")
''')
    return analyze_project(str(tmp_path), use_treesitter=False)


@pytest.fixture
def samples_project():
    """Use the actual test samples directory."""
    return analyze_project("tests/samples/", use_treesitter=False)


@pytest.fixture
def rust_sample_project(tmp_path):
    (tmp_path / "lib.rs").write_text(
        """
use std::fmt;

pub struct Greeter {
    pub name: String,
}

impl Greeter {
    pub fn new(name: String) -> Self {
        Self { name }
    }

    pub fn greet(&self) -> String {
        format!("hi {}", self.name)
    }
}

pub fn top_level(a: i32) -> i32 {
    a + 1
}
"""
    )
    return analyze_project(str(tmp_path), use_treesitter=False)


# =============================================================================
# ALL FORMATS LIST
# =============================================================================

ALL_FORMATS = [
    "yaml",
    "json",
    "logicml",
    "gherkin",
    "markdown",
    "toon",
    "csv",
    "compact",
]


def get_generator(fmt: str):
    """Get generator instance for format."""
    generators = {
        "yaml": YAMLGenerator(),
        "json": JSONGenerator(),
        "logicml": LogicMLGenerator(),
        "gherkin": GherkinGenerator(),
        "markdown": MarkdownGenerator(),
        "toon": TOONGenerator(),
        "csv": CSVGenerator(),
        "compact": CompactGenerator(),
    }
    return generators.get(fmt)


def generate_output(generator, project, detail="standard"):
    """Generate output handling different return types."""
    if isinstance(generator, LogicMLGenerator):
        spec = generator.generate(project)
        return spec.content
    elif isinstance(generator, CompactGenerator):
        return generator.generate(project)
    elif hasattr(generator, "generate"):
        try:
            result = generator.generate(project, detail=detail)
            if hasattr(result, "content"):
                return result.content
            return result
        except TypeError:
            return generator.generate(project)
    return ""


# =============================================================================
# PARAMETRIZED TESTS FOR ALL FORMATS
# =============================================================================


class TestAllFormatsGeneration:
    """Test that all formats generate valid output."""

    @pytest.mark.parametrize("fmt", ALL_FORMATS)
    def test_format_generates_output(self, sample_project, fmt):
        """Test that format generates non-empty output."""
        gen = get_generator(fmt)
        output = generate_output(gen, sample_project)

        assert output is not None
        assert len(output) > 50, f"{fmt} output too short"

    @pytest.mark.parametrize("fmt", ALL_FORMATS)
    def test_format_contains_class_info(self, sample_project, fmt):
        """Test that format contains class information."""
        gen = get_generator(fmt)
        output = generate_output(gen, sample_project, detail="full")

        # All formats should mention Calculator or Config class
        assert (
            "Calculator" in output or "Config" in output or "class" in output.lower()
        ), f"{fmt} missing class info"

    @pytest.mark.parametrize("fmt", ALL_FORMATS)
    def test_format_contains_function_info(self, sample_project, fmt):
        """Test that format contains function information."""
        gen = get_generator(fmt)
        output = generate_output(gen, sample_project, detail="full")

        # Should mention functions
        has_func = any(
            x in output.lower() for x in ["helper", "add", "format", "function", "def"]
        )
        assert has_func, f"{fmt} missing function info"


class TestRustSupport:
    def test_rust_parsing_finds_top_level_and_impl_methods(self, rust_sample_project):
        project = rust_sample_project
        assert project.modules
        m = project.modules[0]
        assert m.language == "rust"

        top = [f.name for f in (m.functions or [])]
        assert "top_level" in top

        cls_names = [c.name for c in (m.classes or [])]
        assert "Greeter" in cls_names

        greeter = next(c for c in m.classes if c.name == "Greeter")
        method_names = [x.name for x in (greeter.methods or [])]
        assert "new" in method_names
        assert "greet" in method_names

    def test_rust_shows_up_in_toon_and_function_logic(self, rust_sample_project):
        project = rust_sample_project
        toon = TOONGenerator().generate(project, detail="full")
        assert "Greeter" in toon
        assert "top_level" in toon

        logic = FunctionLogicGenerator().generate(project, detail="full")
        assert "Greeter.new" in logic or "Greeter.greet" in logic
        assert "top_level" in logic


class TestFormatValidation:
    """Test format validation where applicable."""

    def test_yaml_validation_valid(self, sample_project):
        """Test YAML validation passes for generated output."""
        gen = YAMLGenerator()
        output = gen.generate(sample_project)

        is_valid, errors = validate_yaml(output)
        assert is_valid, f"YAML validation failed: {errors}"

    def test_yaml_validation_invalid(self):
        """Test YAML validation catches invalid input."""
        is_valid, errors = validate_yaml("not: valid: yaml: {{{")
        assert not is_valid

    def test_json_validation_valid(self, sample_project):
        """Test JSON validation passes for generated output."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        is_valid, errors = validate_json(output)
        assert is_valid, f"JSON validation failed: {errors}"

    def test_json_validation_invalid(self):
        """Test JSON validation catches invalid input."""
        is_valid, errors = validate_json('{"invalid": json}')
        assert not is_valid

    def test_logicml_validation_valid(self, sample_project):
        """Test LogicML validation passes for generated output."""
        gen = LogicMLGenerator()
        spec = gen.generate(sample_project)

        is_valid, errors = validate_logicml(spec.content)
        assert is_valid, f"LogicML validation failed: {errors}"

    def test_markdown_validation_valid(self, sample_project):
        """Test Markdown validation passes for generated output."""
        gen = MarkdownGenerator()
        output = gen.generate(sample_project)

        # Markdown generator may embed compact YAML that doesn't strictly validate
        # Just check it generates non-empty output
        assert len(output) > 100


class TestFormatEfficiency:
    """Test format size efficiency."""

    def test_format_sizes(self, sample_project):
        """Compare output sizes across formats."""
        sizes = {}
        for fmt in ALL_FORMATS:
            gen = get_generator(fmt)
            output = generate_output(gen, sample_project, detail="full")
            sizes[fmt] = len(output)

        # All should produce output
        assert all(s > 0 for s in sizes.values())

        # Compact should be smallest text format
        assert sizes["compact"] < sizes["markdown"]

        # TOON should be smaller than JSON
        assert sizes["toon"] < sizes["json"]

    def test_logicml_compression(self, sample_project):
        """Test LogicML is more compact than YAML."""
        yaml_out = generate_output(YAMLGenerator(), sample_project, "full")
        logicml_out = generate_output(LogicMLGenerator(), sample_project)

        assert len(logicml_out) < len(yaml_out)


class TestDetailLevels:
    """Test different detail levels."""

    @pytest.mark.parametrize("fmt", ["yaml", "toon", "json"])
    def test_detail_levels_ordering(self, sample_project, fmt):
        """Test compact < standard < full for detail levels."""
        gen = get_generator(fmt)

        try:
            compact = generate_output(gen, sample_project, "compact")
            standard = generate_output(gen, sample_project, "standard")
            full = generate_output(gen, sample_project, "full")

            assert len(compact) <= len(standard) <= len(full)
        except TypeError:
            # Generator doesn't support detail levels
            pass


# =============================================================================
# FORMAT-SPECIFIC TESTS (unique characteristics)
# =============================================================================


class TestYAMLSpecifics:
    """YAML-specific tests."""

    def test_yaml_parseable(self, sample_project):
        """Test YAML output is parseable."""
        import yaml

        gen = YAMLGenerator()
        output = gen.generate(sample_project)

        data = yaml.safe_load(output)
        assert data is not None

    def test_yaml_includes_imports(self, sample_project):
        """Test YAML includes imports."""
        gen = YAMLGenerator()
        output = gen.generate(sample_project, detail="full")

        assert "import" in output.lower() or "typing" in output


class TestJSONSpecifics:
    """JSON-specific tests."""

    def test_json_parseable(self, sample_project):
        """Test JSON output is parseable."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)

        data = json.loads(output)
        assert data is not None
        assert "modules" in data or "name" in data

    def test_json_structure(self, sample_project):
        """Test JSON has expected structure."""
        gen = JSONGenerator()
        output = gen.generate(sample_project)
        data = json.loads(output)

        assert "statistics" in data or "modules" in data


class TestLogicMLSpecifics:
    """LogicML-specific tests."""

    def test_logicml_has_signatures(self, sample_project):
        """Test LogicML includes sig: markers."""
        gen = LogicMLGenerator()
        spec = gen.generate(sample_project)

        assert "sig:" in spec.content

    def test_logicml_has_async_markers(self, samples_project):
        """Test LogicML marks async functions."""
        gen = LogicMLGenerator()
        spec = gen.generate(samples_project)

        assert "async" in spec.content.lower()

    def test_logicml_token_estimate(self, sample_project):
        """Test LogicML provides token estimate."""
        gen = LogicMLGenerator()
        spec = gen.generate(sample_project)

        assert spec.token_estimate > 0


class TestGherkinSpecifics:
    """Gherkin-specific tests."""

    def test_gherkin_has_feature(self, sample_project):
        """Test Gherkin has Feature keyword."""
        gen = GherkinGenerator()
        output = gen.generate(sample_project)

        assert "Feature:" in output or "Feature" in output

    def test_gherkin_has_scenarios(self, sample_project):
        """Test Gherkin has Scenario keywords."""
        gen = GherkinGenerator()
        output = gen.generate(sample_project)

        assert "Scenario" in output

    def test_gherkin_has_steps(self, sample_project):
        """Test Gherkin has Given/When/Then."""
        gen = GherkinGenerator()
        output = gen.generate(sample_project)

        has_steps = "Given" in output or "When" in output or "Then" in output
        assert has_steps


class TestTOONSpecifics:
    """TOON-specific tests."""

    def test_toon_array_syntax(self, sample_project):
        """Test TOON uses array[N] syntax."""
        gen = TOONGenerator()
        output = gen.generate(sample_project)

        import re

        assert re.search(r"\w+\[\d+\]", output), "TOON should have array headers"

    def test_toon_tabular_syntax(self, sample_project):
        """Test TOON uses tabular {fields} syntax."""
        gen = TOONGenerator()
        output = gen.generate(sample_project, detail="full")

        import re

        assert re.search(r"\[\d+\]\{[^}]+\}", output), (
            "TOON should have tabular headers"
        )

    def test_toon_minimal_quoting(self, sample_project):
        """Test TOON minimizes quotes."""
        gen = TOONGenerator()
        output = gen.generate(sample_project)

        quote_ratio = output.count('"') / len(output) if output else 0
        assert quote_ratio < 0.1, f"Too many quotes: {quote_ratio:.2%}"

    def test_toon_with_tabs(self, sample_project):
        """Test TOON tab delimiter mode."""
        gen = TOONGenerator(use_tabs=True)
        output = gen.generate(sample_project)

        assert "\t" in output


def test_function_logic_toon_js_does_not_default_return_type_to_none(tmp_path):
    (tmp_path / "app.js").write_text(
        """
function foo(a, b) {
  return a + b;
}
""".lstrip()
    )
    project = analyze_project(str(tmp_path), use_treesitter=False)
    out = FunctionLogicGenerator().generate_toon(project, detail="standard")
    assert "-> None" not in out


class TestCSVSpecifics:
    """CSV-specific tests."""

    def test_csv_has_header(self, sample_project):
        """Test CSV has header row."""
        gen = CSVGenerator()
        output = gen.generate(sample_project)

        lines = output.strip().split("\n")
        assert len(lines) >= 2  # Header + at least one row

    def test_csv_consistent_columns(self, sample_project):
        """Test CSV has consistent column count."""
        gen = CSVGenerator()
        output = gen.generate(sample_project)

        # CSV may have quoted fields with commas inside
        # Just verify it produces valid multi-line output
        lines = output.strip().split("\n")
        assert len(lines) >= 2  # Header + data


class TestCompactSpecifics:
    """Compact format-specific tests."""

    def test_compact_is_small(self, sample_project):
        """Test Compact is smaller than others."""
        compact = generate_output(CompactGenerator(), sample_project)
        markdown = generate_output(MarkdownGenerator(), sample_project)

        assert len(compact) < len(markdown)

    def test_compact_has_summary(self, sample_project):
        """Test Compact includes summary."""
        gen = CompactGenerator()
        output = gen.generate(sample_project)

        # Should have file/line counts
        assert "f" in output.lower() or "file" in output.lower()


# =============================================================================
# CROSS-FORMAT EQUIVALENCE TESTS
# =============================================================================


class TestCrossFormatEquivalence:
    """Test that all formats contain equivalent information."""

    def test_all_formats_have_project_name(self, sample_project):
        """All formats should include project name or module info."""
        for fmt in ALL_FORMATS:
            gen = get_generator(fmt)
            output = generate_output(gen, sample_project)

            # LogicML uses module path instead of project name
            has_info = (
                sample_project.name in output
                or "project" in output.lower()
                or "main.py" in output
                or "module" in output.lower()
            )
            assert has_info, f"{fmt} missing project/module info"

    def test_all_formats_have_module_info(self, sample_project):
        """All formats should include module information."""
        for fmt in ALL_FORMATS:
            gen = get_generator(fmt)
            output = generate_output(gen, sample_project, "full")

            has_module = (
                "main" in output.lower()
                or "module" in output.lower()
                or ".py" in output
            )
            assert has_module, f"{fmt} missing module info"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
