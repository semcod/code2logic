"""
Comprehensive tests for error handling during project analysis.

Tests all potential errors that can occur:
- Filesystem errors (permission, not found, encoding, etc.)
- Parsing errors (syntax, timeout, binary files)
- Generation errors (serialization, output write)
- System errors (memory, timeout)
"""

import pytest
import os
from pathlib import Path

from code2logic.errors import (
    ErrorHandler,
    ErrorType,
    ErrorSeverity,
    AnalysisError,
    AnalysisResult,
)
from code2logic import analyze_project, YAMLGenerator, JSONGenerator


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def error_handler():
    """Create a default error handler."""
    return ErrorHandler(mode="lenient")


@pytest.fixture
def strict_handler():
    """Create a strict error handler."""
    return ErrorHandler(mode="strict")


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with various files."""
    # Normal Python file
    (tmp_path / "normal.py").write_text("def hello(): pass")

    # Empty file
    (tmp_path / "empty.py").write_text("")

    # Valid Python with syntax
    (tmp_path / "valid.py").write_text("""
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
""")

    return tmp_path


# =============================================================================
# FILESYSTEM ERROR TESTS
# =============================================================================


class TestFilesystemErrors:
    """Tests for filesystem-related errors."""

    def test_file_not_found(self, error_handler):
        """Test handling of missing files."""
        result = error_handler.safe_read_file(Path("/nonexistent/file.py"))

        assert result is None
        assert error_handler.result.has_errors()
        assert any(
            e.type == ErrorType.FILE_NOT_FOUND for e in error_handler.result.errors
        )

    @pytest.mark.skipif(os.name == "nt", reason="Unix permissions only")
    def test_permission_denied(self, error_handler, tmp_path):
        """Test handling of permission denied."""
        # Create file with no read permission
        test_file = tmp_path / "no_read.py"
        test_file.write_text("content")
        test_file.chmod(0o000)

        try:
            result = error_handler.safe_read_file(test_file)
            assert result is None
            assert any(
                e.type == ErrorType.PERMISSION_DENIED
                for e in error_handler.result.errors
            )
        finally:
            test_file.chmod(0o644)

    def test_file_too_large(self, tmp_path):
        """Test handling of files exceeding size limit."""
        handler = ErrorHandler(max_file_size_mb=0.001)  # 1KB limit

        # Create file larger than limit
        large_file = tmp_path / "large.py"
        large_file.write_text("x" * 2000)  # 2KB

        result = handler.safe_read_file(large_file)

        assert result is None
        assert any(e.type == ErrorType.FILE_TOO_LARGE for e in handler.result.errors)

    def test_binary_file_detection(self, error_handler, tmp_path):
        """Test detection of binary files."""
        binary_file = tmp_path / "binary.py"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x04")

        result = error_handler.safe_read_file(binary_file)

        assert result is None
        assert any(
            e.type == ErrorType.BINARY_FILE for e in error_handler.result.warnings
        )

    def test_encoding_fallback(self, error_handler, tmp_path):
        """Test encoding fallback for non-UTF8 files."""
        # Create file with Latin-1 encoding (using chars valid in latin-1)
        latin1_file = tmp_path / "latin1.py"
        latin1_file.write_bytes(
            "# Caf\xe9 cr\xe8me\ndef hello(): pass".encode("latin-1")
        )

        result = error_handler.safe_read_file(latin1_file)

        # Should successfully read with fallback encoding
        assert result is not None
        assert "hello" in result

    def test_empty_file(self, error_handler, tmp_path):
        """Test handling of empty files."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        result = error_handler.safe_read_file(empty_file)

        # Empty file should be read successfully (empty string)
        assert result == ""


# =============================================================================
# PARSING ERROR TESTS
# =============================================================================


class TestParsingErrors:
    """Tests for parsing-related errors."""

    def test_syntax_error_in_python(self, error_handler, tmp_path):
        """Test handling of Python syntax errors."""
        syntax_file = tmp_path / "syntax_error.py"
        syntax_file.write_text("""
def broken(
    # Missing closing parenthesis
class Foo:
    pass
""")

        # Read file successfully
        content = error_handler.safe_read_file(syntax_file)
        assert content is not None

        # Parse should handle error gracefully
        def mock_parser(path, content, lang):
            raise SyntaxError("invalid syntax")

        result = error_handler.safe_parse("test.py", content, mock_parser, "python")
        assert result is None
        assert any(
            e.type == ErrorType.SYNTAX_ERROR for e in error_handler.result.errors
        )

    def test_deeply_nested_code(self, error_handler):
        """Test handling of deeply nested code that may cause recursion."""

        def mock_parser(path, content, lang):
            raise RecursionError("maximum recursion depth exceeded")

        result = error_handler.safe_parse("deep.py", "content", mock_parser, "python")

        assert result is None
        assert any(
            e.type == ErrorType.PARSE_TIMEOUT for e in error_handler.result.errors
        )

    def test_unsupported_language(self, error_handler):
        """Test handling of unsupported languages."""
        error_handler.handle_error(
            ErrorType.UNSUPPORTED_LANGUAGE, "file.xyz", "Language xyz not supported"
        )

        # Should be warning, not error
        assert len(error_handler.result.warnings) > 0
        assert error_handler.result.warnings[0].type == ErrorType.UNSUPPORTED_LANGUAGE


# =============================================================================
# GENERATION ERROR TESTS
# =============================================================================


class TestGenerationErrors:
    """Tests for output generation errors."""

    def test_yaml_with_special_characters(self, temp_project):
        """Test YAML generation with special characters."""
        # Add file with special characters in docstring
        special_file = temp_project / "special.py"
        special_file.write_text('''
def process():
    """Process data with special chars: @#$%^&*(){}[]|\\:;"'<>,.?/"""
    pass
''')

        project = analyze_project(str(temp_project), use_treesitter=False)
        gen = YAMLGenerator()

        # Should not raise
        result = gen.generate(project)
        assert len(result) > 0

    def test_json_with_unicode(self, temp_project):
        """Test JSON generation with unicode."""
        unicode_file = temp_project / "unicode.py"
        unicode_file.write_text('''
def pozdrowienia():
    """Cześć świecie! 你好世界! مرحبا بالعالم"""
    return "🎉"
''')

        project = analyze_project(str(temp_project), use_treesitter=False)
        gen = JSONGenerator()

        # Should not raise
        result = gen.generate(project)
        assert len(result) > 0

    def test_write_to_readonly_location(self, error_handler, tmp_path):
        """Test writing to read-only location."""
        if os.name == "nt":
            pytest.skip("Unix permissions only")

        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o555)

        try:
            result = error_handler.safe_write_file(
                readonly_dir / "output.yaml", "content"
            )
            assert result is False
            assert any(
                e.type == ErrorType.PERMISSION_DENIED
                for e in error_handler.result.errors
            )
        finally:
            readonly_dir.chmod(0o755)

    def test_write_creates_directories(self, error_handler, tmp_path):
        """Test that write creates parent directories."""
        deep_path = tmp_path / "a" / "b" / "c" / "output.yaml"

        result = error_handler.safe_write_file(deep_path, "content")

        assert result is True
        assert deep_path.exists()
        assert deep_path.read_text() == "content"


# =============================================================================
# ERROR HANDLER MODES
# =============================================================================


class TestErrorHandlerModes:
    """Tests for different error handler modes."""

    def test_lenient_mode_continues(self, tmp_path):
        """Test that lenient mode continues on errors."""
        handler = ErrorHandler(mode="lenient")

        # Add multiple errors
        handler.handle_error(ErrorType.FILE_NOT_FOUND, "a.py", "Not found")
        handler.handle_error(ErrorType.PERMISSION_DENIED, "b.py", "Denied")
        handler.handle_error(ErrorType.SYNTAX_ERROR, "c.py", "Syntax")

        # All should continue
        assert len(handler.result.errors) == 3

    def test_strict_mode_stops(self, tmp_path):
        """Test that strict mode stops on first error."""
        handler = ErrorHandler(mode="strict")

        # First error should return False
        should_continue = handler.handle_error(
            ErrorType.FILE_NOT_FOUND, "a.py", "Not found"
        )

        assert should_continue is False

    def test_silent_mode_no_logging(self, tmp_path, caplog):
        """Test that silent mode doesn't log."""
        handler = ErrorHandler(mode="silent")

        handler.handle_error(ErrorType.FILE_NOT_FOUND, "a.py", "Not found")

        # Error should be recorded but not logged
        assert len(handler.result.errors) == 1

    def test_critical_error_stops_all_modes(self):
        """Test that critical errors stop processing in all modes."""
        for mode in ["lenient", "strict", "silent"]:
            handler = ErrorHandler(mode=mode)

            should_continue = handler.handle_error(
                ErrorType.MEMORY_ERROR,
                "file.py",
                "Out of memory",
                severity=ErrorSeverity.CRITICAL,
            )

            assert should_continue is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests for error handling during full analysis."""

    def test_mixed_valid_invalid_files(self, tmp_path):
        """Test analysis with mix of valid and problematic files."""
        # Valid file
        (tmp_path / "valid.py").write_text("def hello(): pass")

        # Binary file (should be skipped)
        (tmp_path / "binary.py").write_bytes(b"\x00\x01\x02")

        # Empty file (should be included)
        (tmp_path / "empty.py").write_text("")

        # Valid complex file
        (tmp_path / "complex.py").write_text("""
class Service:
    def __init__(self):
        self.data = []
    
    async def process(self, items: list) -> dict:
        return {"count": len(items)}
""")

        project = analyze_project(str(tmp_path), use_treesitter=False)

        # Should have processed valid files
        assert project.total_files >= 2

    def test_nested_folders_with_errors(self, tmp_path):
        """Test analysis of nested folders with various errors."""
        # Create nested structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "core").mkdir()
        (tmp_path / "src" / "utils").mkdir()

        # Add valid files
        (tmp_path / "src" / "core" / "main.py").write_text("def main(): pass")
        (tmp_path / "src" / "utils" / "helpers.py").write_text("def help(): pass")

        # Add empty __init__.py files
        (tmp_path / "src" / "__init__.py").write_text("")
        (tmp_path / "src" / "core" / "__init__.py").write_text("from .main import main")

        project = analyze_project(str(tmp_path), use_treesitter=False)

        # Should process all Python files
        assert project.total_files >= 3

    def test_large_project_resilience(self, tmp_path):
        """Test resilience with many files."""
        # Create 50 files
        for i in range(50):
            content = f"def func_{i}(): return {i}"
            (tmp_path / f"module_{i}.py").write_text(content)

        project = analyze_project(str(tmp_path), use_treesitter=False)

        assert project.total_files == 50

        # Generate YAML should work
        gen = YAMLGenerator()
        yaml_output = gen.generate(project)
        assert len(yaml_output) > 0


# =============================================================================
# ERROR RESULT TESTS
# =============================================================================


class TestAnalysisResult:
    """Tests for AnalysisResult class."""

    def test_result_summary(self):
        """Test result summary generation."""
        result = AnalysisResult()
        result.processed_files = 10
        result.total_files = 12
        result.skipped_files = ["a.py", "b.py"]
        result.errors.append(
            AnalysisError(
                type=ErrorType.FILE_NOT_FOUND,
                severity=ErrorSeverity.ERROR,
                path="c.py",
                message="Not found",
            )
        )

        summary = result.summary()

        assert "10/12" in summary
        assert "Errors: 1" in summary
        assert "Skipped: 2" in summary

    def test_error_to_dict(self):
        """Test error serialization."""
        error = AnalysisError(
            type=ErrorType.SYNTAX_ERROR,
            severity=ErrorSeverity.ERROR,
            path="test.py",
            message="Invalid syntax",
            exception="SyntaxError: unexpected EOF",
            suggestion="Fix the syntax error",
        )

        data = error.to_dict()

        assert data["type"] == "syntax_error"
        assert data["severity"] == "error"
        assert data["path"] == "test.py"
        assert "suggestion" in data


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    def test_very_long_lines(self, tmp_path):
        """Test handling of files with very long lines."""
        long_line_file = tmp_path / "long_lines.py"
        long_line = "x = '" + "a" * 10000 + "'"
        long_line_file.write_text(long_line)

        project = analyze_project(str(tmp_path), use_treesitter=False)

        # Should process without crashing
        assert project.total_files == 1

    def test_many_functions(self, tmp_path):
        """Test handling of file with many functions."""
        many_funcs_file = tmp_path / "many_funcs.py"
        funcs = "\n".join([f"def func_{i}(): pass" for i in range(500)])
        many_funcs_file.write_text(funcs)

        project = analyze_project(str(tmp_path), use_treesitter=False)

        # Should process and find functions
        assert project.total_files == 1
        assert len(project.modules[0].functions) > 0

    def test_deeply_nested_classes(self, tmp_path):
        """Test handling of deeply nested classes."""
        nested_file = tmp_path / "nested.py"
        nested_file.write_text("""
class Level1:
    class Level2:
        class Level3:
            def method(self):
                pass
""")

        project = analyze_project(str(tmp_path), use_treesitter=False)

        # Should process without crashing
        assert project.total_files == 1

    def test_circular_imports_reference(self, tmp_path):
        """Test handling of files with circular import patterns."""
        (tmp_path / "a.py").write_text("from b import B\nclass A: pass")
        (tmp_path / "b.py").write_text("from a import A\nclass B: pass")

        project = analyze_project(str(tmp_path), use_treesitter=False)

        # Should analyze both files
        assert project.total_files == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
