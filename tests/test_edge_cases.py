"""Additional tests for code2flow - edge cases and integration tests."""

import pytest
import tempfile
import shutil
from pathlib import Path
from code2flow import ProjectAnalyzer, FAST_CONFIG, NLPPipeline, FAST_NLP_CONFIG
from code2flow.core.analyzer import FileCache, FastFileFilter
from code2flow.core.config import FilterConfig


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_project(self):
        """Analyze empty project directory."""
        empty_dir = tempfile.mkdtemp()
        try:
            analyzer = ProjectAnalyzer(FAST_CONFIG)
            result = analyzer.analyze_project(empty_dir)

            assert result.get_function_count() == 0
            assert result.get_class_count() == 0
            assert result.stats["files_processed"] == 0
        finally:
            shutil.rmtree(empty_dir)

    def test_nonexistent_path(self):
        """Handle non-existent path gracefully."""
        analyzer = ProjectAnalyzer(FAST_CONFIG)

        with pytest.raises((FileNotFoundError, OSError)):
            analyzer.analyze_project("/nonexistent/path/12345")

    def test_syntax_error_file(self):
        """Handle Python file with syntax errors."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Create file with syntax error
            (tmp_dir / "broken.py").write_text("def foo(:\n  pass")

            # Create valid file
            (tmp_dir / "valid.py").write_text("def bar(): pass")

            analyzer = ProjectAnalyzer(FAST_CONFIG)
            result = analyzer.analyze_project(str(tmp_dir))

            # Should process valid file, skip broken one
            assert result.stats["files_processed"] >= 1
        finally:
            shutil.rmtree(tmp_dir)

    def test_very_large_file(self):
        """Handle very large Python file."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Create large file (1000 functions)
            lines = [f"def func_{i}(): pass" for i in range(1000)]
            (tmp_dir / "large.py").write_text("\n".join(lines))

            analyzer = ProjectAnalyzer(FAST_CONFIG)
            result = analyzer.analyze_project(str(tmp_dir))

            assert result.get_function_count() >= 1000
        finally:
            shutil.rmtree(tmp_dir)

    def test_unicode_filenames(self):
        """Handle files with unicode names."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Create file with unicode name
            (tmp_dir / "tëst_файл.py").write_text("def foo(): pass")

            analyzer = ProjectAnalyzer(FAST_CONFIG)
            result = analyzer.analyze_project(str(tmp_dir))

            assert result.get_function_count() >= 1
        finally:
            shutil.rmtree(tmp_dir)

    def test_nested_classes(self):
        """Handle deeply nested class structures."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            code = """
class Outer:
    class Middle:
        class Inner:
            def method(self): pass
"""
            (tmp_dir / "nested.py").write_text(code)

            analyzer = ProjectAnalyzer(FAST_CONFIG)
            result = analyzer.analyze_project(str(tmp_dir))

            # Should find all nested classes
            assert result.get_class_count() >= 3
        finally:
            shutil.rmtree(tmp_dir)

    def test_decorators(self):
        """Handle various decorator patterns."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            code = """
@property
def foo(): pass

@decorator(arg)
def bar(): pass

@decorator1
@decorator2
def baz(): pass
"""
            (tmp_dir / "decorated.py").write_text(code)

            analyzer = ProjectAnalyzer(FAST_CONFIG)
            result = analyzer.analyze_project(str(tmp_dir))

            assert result.get_function_count() >= 3
        finally:
            shutil.rmtree(tmp_dir)


class TestFileCache:
    """Test caching functionality."""

    def test_cache_hit(self):
        """Test cache hit returns cached result."""
        cache = FileCache(cache_dir=tempfile.mkdtemp(), ttl_hours=24)

        content = "test content"
        file_path = "/test/file.py"

        # First call - cache miss
        import ast

        tree = ast.parse("def foo(): pass")
        cache.put(file_path, content, (tree, content))

        # Second call - cache hit
        cached = cache.get(file_path, content)
        assert cached is not None

        shutil.rmtree(cache.cache_dir)

    def test_cache_ttl_expiration(self):
        """Test cache entries expire after TTL."""
        cache_dir = tempfile.mkdtemp()
        cache = FileCache(cache_dir=cache_dir, ttl_hours=0)  # Immediate expiration

        content = "test"
        file_path = "/test/file.py"

        import ast

        tree = ast.parse("def foo(): pass")
        cache.put(file_path, content, (tree, content))

        # Should be expired
        cached = cache.get(file_path, content)
        assert cached is None

        shutil.rmtree(cache_dir)

    def test_cache_clear(self):
        """Test cache clear removes all entries."""
        cache_dir = tempfile.mkdtemp()
        cache = FileCache(cache_dir=cache_dir)

        # Add entries
        import ast

        for i in range(5):
            tree = ast.parse(f"def foo{i}(): pass")
            cache.put(f"/test/{i}.py", f"content{i}", (tree, f"content{i}"))

        # Clear
        cache.clear()

        # Verify cleared
        assert len(list(Path(cache_dir).glob("*.pkl"))) == 0

        shutil.rmtree(cache_dir)


class TestFiltering:
    """Test file and function filtering."""

    def test_exclude_tests(self):
        """Test test file exclusion."""
        config = FilterConfig(exclude_tests=True)
        filter_obj = FastFileFilter(config)

        assert not filter_obj.should_process("/path/test_something.py")
        assert not filter_obj.should_process("/path/something_test.py")
        assert filter_obj.should_process("/path/production.py")

    def test_exclude_patterns(self):
        """Test custom exclude patterns."""
        config = FilterConfig(exclude_patterns=["*legacy*", "*backup*"])
        filter_obj = FastFileFilter(config)

        assert not filter_obj.should_process("/path/legacy_code.py")
        assert not filter_obj.should_process("/path/backup_2023.py")
        assert filter_obj.should_process("/path/current.py")

    def test_skip_private_methods(self):
        """Test private method filtering."""
        config = FilterConfig(skip_private=True, min_function_lines=1)
        filter_obj = FastFileFilter(config)

        # Private methods should be skipped
        assert filter_obj.should_skip_function("_private", 5, is_private=True)
        assert not filter_obj.should_skip_function("public", 5, is_private=False)

    def test_skip_properties(self):
        """Test property filtering."""
        config = FilterConfig(skip_properties=True)
        filter_obj = FastFileFilter(config)

        assert filter_obj.should_skip_function("prop", 3, is_property=True)


class TestNLPEdgeCases:
    """Test NLP pipeline edge cases."""

    def test_empty_query(self):
        """Handle empty query."""
        pipeline = NLPPipeline(FAST_NLP_CONFIG)
        result = pipeline.process("")

        assert result.fallback_used is True
        assert result.overall_confidence < 0.5

    def test_gibberish_query(self):
        """Handle gibberish/nonsense query."""
        pipeline = NLPPipeline(FAST_NLP_CONFIG)
        result = pipeline.process("xyz abc 123 !!! @#$%")

        assert result.fallback_used is True
        assert result.get_intent() == "generic_search"

    def test_very_long_query(self):
        """Handle very long query."""
        long_query = "find function " + "a" * 1000

        pipeline = NLPPipeline(FAST_NLP_CONFIG)
        result = pipeline.process(long_query)

        # Should not crash
        assert result.normalized_query is not None

    def test_mixed_languages(self):
        """Handle mixed language query."""
        pipeline = NLPPipeline(FAST_NLP_CONFIG)

        # Mixed EN/PL
        result = pipeline.process("find funkcję test", language="en")
        assert result.get_intent() is not None

    def test_special_characters(self):
        """Handle query with special characters."""
        pipeline = NLPPipeline(FAST_NLP_CONFIG)

        queries = [
            "find function <test>",
            "show {call} graph",
            "analyze [flow]",
        ]

        for query in queries:
            result = pipeline.process(query)
            assert result.normalized_query is not None


class TestIntegration:
    """Integration tests combining analysis and NLP."""

    def test_codebase_entity_resolution(self):
        """Resolve entities from actual codebase."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Create test codebase
            (tmp_dir / "module.py").write_text("""
class TestClass:
    def test_method(self): pass

def standalone_func(): pass
""")

            # Analyze
            analyzer = ProjectAnalyzer(FAST_CONFIG)
            analysis = analyzer.analyze_project(str(tmp_dir))

            # Load entities
            from code2flow.nlp import EntityResolver

            resolver = EntityResolver()
            resolver.load_from_analysis(analysis)

            # Resolve
            result = resolver.resolve("find TestClass")
            assert len(result.entities) > 0

        finally:
            shutil.rmtree(tmp_dir)

    def test_nlp_to_analysis_workflow(self):
        """Complete workflow: NLP query -> code analysis."""
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Create test codebase
            (tmp_dir / "app.py").write_text("""
def process_data(data):
    return data * 2

def validate_input(x):
    return x > 0
""")

            # Step 1: NLP process query
            pipeline = NLPPipeline(FAST_NLP_CONFIG)
            nlp_result = pipeline.process("find function process_data")

            assert nlp_result.get_intent() == "find_function"

            # Step 2: Analyze code
            analyzer = ProjectAnalyzer(FAST_CONFIG)
            analysis = analyzer.analyze_project(str(tmp_dir))

            # Step 3: Verify function exists
            func_names = [f.name for f in analysis.functions.values()]
            assert "process_data" in func_names

        finally:
            shutil.rmtree(tmp_dir)


class TestBenchmarks:
    """Performance benchmarks."""

    def test_analysis_performance(self):
        """Benchmark analysis speed."""
        import time

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Create medium-sized codebase
            for i in range(50):
                (tmp_dir / f"module_{i}.py").write_text("""
def func_a(): pass
def func_b(): pass
def func_c(): pass
class ClassX: pass
""")

            analyzer = ProjectAnalyzer(FAST_CONFIG)

            start = time.time()
            result = analyzer.analyze_project(str(tmp_dir))
            elapsed = time.time() - start

            # Should complete in reasonable time (< 30s)
            assert elapsed < 30.0
            assert result.get_function_count() >= 150  # 50 * 3 functions

        finally:
            shutil.rmtree(tmp_dir)

    def test_nlp_performance(self):
        """Benchmark NLP pipeline speed."""
        import time

        pipeline = NLPPipeline(FAST_NLP_CONFIG)

        queries = ["find function test", "show call graph", "analyze flow"] * 100

        start = time.time()
        for query in queries:
            pipeline.process(query)
        elapsed = time.time() - start

        # Should process 300 queries in < 10s
        assert elapsed < 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
