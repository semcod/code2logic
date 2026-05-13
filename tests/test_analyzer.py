"""Test suite for code2flow."""

import pytest
import tempfile
import shutil
from pathlib import Path
from code2flow import ProjectAnalyzer
from code2flow.core.config import FAST_CONFIG


class TestProjectAnalyzer:
    """Test the main ProjectAnalyzer."""

    @pytest.fixture
    def sample_project(self):
        """Create a temporary sample project."""
        project_dir = Path(tempfile.mkdtemp())

        # Create sample module
        (project_dir / "module1.py").write_text('''
def process_data(data):
    """Process data."""
    if not data:
        return None
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result

def validate(data):
    return isinstance(data, list)
''')

        # Create class module
        (project_dir / "module2.py").write_text('''
class Connection:
    """Connection state machine."""
    
    def __init__(self):
        self.state = "disconnected"
    
    def connect(self):
        if self.state == "disconnected":
            self.state = "connecting"
    
    def connected(self):
        if self.state == "connecting":
            self.state = "connected"
''')

        # Create recursive module
        (project_dir / "module3.py").write_text('''
def factorial(n):
    """Recursive factorial."""
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
''')

        yield project_dir

        # Cleanup
        shutil.rmtree(project_dir)

    def test_analyze_finds_functions(self, sample_project):
        """Test that analyzer finds all functions."""
        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(str(sample_project))

        assert result.get_function_count() >= 6
        assert "factorial" in [f.name for f in result.functions.values()]
        assert "process_data" in [f.name for f in result.functions.values()]

    def test_analyze_finds_classes(self, sample_project):
        """Test that analyzer finds classes."""
        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(str(sample_project))

        assert result.get_class_count() >= 1
        assert "Connection" in [c.name for c in result.classes.values()]

    def test_detects_recursion(self, sample_project):
        """Test recursion detection."""
        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(str(sample_project))

        recursive_patterns = [p for p in result.patterns if p.type == "recursion"]
        assert len(recursive_patterns) >= 2

        func_names = [p.name for p in recursive_patterns]
        assert any("factorial" in n for n in func_names)
        assert any("fibonacci" in n for n in func_names)

    def test_detects_state_machine(self, sample_project):
        """Test state machine detection."""
        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(str(sample_project))

        state_patterns = [p for p in result.patterns if p.type == "state_machine"]
        assert len(state_patterns) >= 1
        assert any("Connection" in p.name for p in state_patterns)

    def test_caching_works(self, sample_project):
        """Test that caching improves performance."""
        config = FAST_CONFIG
        config.performance.enable_cache = True
        config.performance.cache_dir = str(sample_project / ".cache")

        # First run - populate cache
        analyzer1 = ProjectAnalyzer(config)
        result1 = analyzer1.analyze_project(str(sample_project))

        # Second run - should use cache
        analyzer2 = ProjectAnalyzer(config)
        result2 = analyzer2.analyze_project(str(sample_project))

        assert result2.stats.get("cache_hits", 0) > 0

    def test_filtering_skips_tests(self, sample_project):
        """Test that test files are filtered out."""
        # Create test file
        (sample_project / "test_module.py").write_text("""
def test_something():
    assert True
""")

        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(str(sample_project))

        # Should not include test functions
        func_names = [f.name for f in result.functions.values()]
        assert "test_something" not in func_names


class TestConfig:
    """Test configuration."""

    def test_fast_config_limits_depth(self):
        """Test that FAST_CONFIG limits analysis depth."""
        assert FAST_CONFIG.depth.max_cfg_depth <= 3
        assert FAST_CONFIG.depth.max_call_depth <= 2
        assert FAST_CONFIG.performance.fast_mode is True

    def test_fast_config_skips_private(self):
        """Test that FAST_CONFIG skips private functions."""
        assert FAST_CONFIG.filters.skip_private is True


class TestExporters:
    """Test export functionality."""

    @pytest.fixture
    def sample_result(self):
        """Create sample analysis result."""
        from code2flow.core.models import AnalysisResult, FunctionInfo

        result = AnalysisResult(
            project_path="/test",
            analysis_mode="static",
        )
        result.functions["test.func1"] = FunctionInfo(
            name="func1",
            qualified_name="test.func1",
            file="/test/file.py",
            line=1,
            calls=["test.func2"],
        )
        result.functions["test.func2"] = FunctionInfo(
            name="func2",
            qualified_name="test.func2",
            file="/test/file.py",
            line=5,
            called_by=["test.func1"],
        )
        return result

    def test_json_export(self, sample_result, tmp_path):
        """Test JSON export."""
        from code2flow.exporters.base import JSONExporter

        output = tmp_path / "output.json"
        exporter = JSONExporter()
        exporter.export(sample_result, str(output), compact=True)

        assert output.exists()
        content = output.read_text()
        assert "test.func1" in content
        assert "test.func2" in content

    def test_mermaid_export(self, sample_result, tmp_path):
        """Test Mermaid export."""
        from code2flow.exporters.base import MermaidExporter

        output = tmp_path / "output.mmd"
        exporter = MermaidExporter()
        exporter.export(sample_result, str(output))

        assert output.exists()
        content = output.read_text()
        assert "flowchart TD" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
