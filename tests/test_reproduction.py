"""
Tests for code reproduction functionality.

Tests format generation, reproduction quality, and cross-language support.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from code2logic import (
    analyze_project,
    ReproductionMetrics,
)
from code2logic.generators import YAMLGenerator
from code2logic.gherkin import GherkinGenerator
from code2logic.markdown_format import MarkdownHybridGenerator
from code2logic.logicml import LogicMLGenerator, generate_logicml
from code2logic.chunked_reproduction import (
    chunk_spec,
    get_llm_limit,
    estimate_tokens,
)


class TestYAMLGenerator:
    """Tests for YAML format generation."""

    def test_yaml_basic(self):
        """Test basic YAML generation."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = YAMLGenerator()
        result = gen.generate(project)

        assert result
        assert "modules" in result or "project" in result

    def test_yaml_includes_classes(self):
        """Test YAML includes class information."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = YAMLGenerator()
        result = gen.generate(project, detail="full")

        # Should contain class info from sample_class.py
        assert "Calculator" in result or "class" in result.lower()

    def test_yaml_includes_functions(self):
        """Test YAML includes function information."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = YAMLGenerator()
        result = gen.generate(project, detail="full")

        # Should contain function info
        assert "calculate" in result.lower() or "function" in result.lower()


class TestGherkinGenerator:
    """Tests for Gherkin format generation."""

    def test_gherkin_basic(self):
        """Test basic Gherkin generation."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = GherkinGenerator()
        result = gen.generate(project)

        assert result
        assert "Feature" in result or "Scenario" in result

    def test_gherkin_has_scenarios(self):
        """Test Gherkin has scenarios."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = GherkinGenerator()
        result = gen.generate(project)

        assert "Scenario" in result or "Given" in result


class TestMarkdownGenerator:
    """Tests for Markdown hybrid format generation."""

    def test_markdown_basic(self):
        """Test basic Markdown generation."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = MarkdownHybridGenerator()
        result = gen.generate(project)

        assert result
        assert result.content

    def test_markdown_has_yaml_section(self):
        """Test Markdown has YAML section."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = MarkdownHybridGenerator()
        result = gen.generate(project)

        # Should have embedded YAML
        assert "```yaml" in result.content or "yaml" in result.content.lower()


class TestReproductionMetrics:
    """Tests for reproduction metrics calculation."""

    def test_metrics_basic(self):
        """Test basic metrics calculation."""
        original = "def hello(): pass"
        generated = "def hello(): pass"
        spec = "function: hello"

        metrics = ReproductionMetrics()
        result = metrics.analyze(original, generated, spec)

        assert result.overall_score > 0

    def test_metrics_identical_code(self):
        """Test metrics for identical code."""
        code = """
def add(a, b):
    return a + b
"""
        metrics = ReproductionMetrics()
        result = metrics.analyze(code, code, "spec")

        # Identical code should have high score
        assert result.overall_score >= 80

    def test_metrics_different_code(self):
        """Test metrics for different code."""
        original = "def foo(): return 1"
        generated = "def bar(): return 2"

        metrics = ReproductionMetrics()
        result = metrics.analyze(original, generated, "spec")

        # Different code should have lower score
        assert result.overall_score < 100


class TestChunkedReproduction:
    """Tests for chunked reproduction functionality."""

    def test_estimate_tokens(self):
        """Test token estimation."""
        text = "Hello world" * 100  # ~1100 chars
        tokens = estimate_tokens(text)

        # ~4 chars per token
        assert 200 <= tokens <= 400

    def test_get_llm_limit(self):
        """Test LLM limit detection."""
        assert get_llm_limit("gpt-4") == 8000
        assert get_llm_limit("llama-7b") == 2000
        assert get_llm_limit("claude-3") == 100000
        assert get_llm_limit("unknown-model") == 4000  # default

    def test_chunk_yaml_spec(self):
        """Test YAML spec chunking."""
        spec = """
project: test
modules:
  - path: file1.py
    classes:
      - name: Class1
  - path: file2.py
    functions:
      - name: func1
"""
        result = chunk_spec(spec, "yaml", max_tokens=50)

        assert result.chunks
        assert result.total_tokens > 0

    def test_chunk_gherkin_spec(self):
        """Test Gherkin spec chunking."""
        spec = """
Feature: Calculator
  Scenario: Add numbers
    Given two numbers
    When I add them
    Then I get the sum

Feature: User
  Scenario: Create user
    Given user data
    When I create user
    Then user exists
"""
        result = chunk_spec(spec, "gherkin", max_tokens=50)

        assert result.chunks
        assert result.format == "gherkin"


class TestProjectAnalysis:
    """Tests for project analysis."""

    def test_analyze_samples(self):
        """Test analyzing samples directory."""
        project = analyze_project("tests/samples/", use_treesitter=False)

        assert project.total_files > 0
        assert project.total_lines > 0
        assert len(project.modules) > 0

    def test_analyze_detects_classes(self):
        """Test that analysis detects classes."""
        project = analyze_project("tests/samples/", use_treesitter=False)

        classes_found = sum(len(m.classes) for m in project.modules)
        assert classes_found > 0

    def test_analyze_detects_functions(self):
        """Test that analysis detects functions."""
        project = analyze_project("tests/samples/", use_treesitter=False)

        functions_found = sum(len(m.functions) for m in project.modules)
        assert functions_found > 0


class TestLogicMLGenerator:
    """Tests for LogicML format generation."""

    def test_logicml_basic(self):
        """Test basic LogicML generation."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = LogicMLGenerator()
        result = gen.generate(project)

        assert result.content
        assert result.token_estimate > 0

    def test_logicml_includes_classes(self):
        """Test LogicML includes class information."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = LogicMLGenerator()
        result = gen.generate(project)

        assert "Calculator" in result.content or "class" in result.content.lower()

    def test_logicml_includes_signatures(self):
        """Test LogicML includes function signatures."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        gen = LogicMLGenerator()
        result = gen.generate(project)

        assert "sig:" in result.content

    def test_logicml_convenience_function(self):
        """Test generate_logicml convenience function."""
        project = analyze_project("tests/samples/", use_treesitter=False)
        result = generate_logicml(project)

        assert result
        assert len(result) > 100


class TestFormatComparison:
    """Tests comparing different formats."""

    def test_yaml_compact(self):
        """Test that YAML produces compact output."""
        project = analyze_project("tests/samples/", use_treesitter=False)

        yaml_gen = YAMLGenerator()
        yaml_spec = yaml_gen.generate(project)

        # YAML should be reasonably compact
        assert len(yaml_spec) > 100
        # And contain structured data
        assert "modules" in yaml_spec or "functions" in yaml_spec

    def test_all_formats_produce_output(self):
        """Test all formats produce non-empty output."""
        project = analyze_project("tests/samples/", use_treesitter=False)

        yaml_gen = YAMLGenerator()
        gherkin_gen = GherkinGenerator()
        md_gen = MarkdownHybridGenerator()

        assert len(yaml_gen.generate(project)) > 100
        assert len(gherkin_gen.generate(project)) > 100
        assert len(md_gen.generate(project).content) > 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
