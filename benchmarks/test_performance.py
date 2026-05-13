"""Performance benchmarks for code2flow."""

import tempfile
import shutil
import time
from pathlib import Path

import pytest

from code2flow import ProjectAnalyzer
from code2flow.core.config import FAST_CONFIG


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def large_project(self):
        """Create a larger project for benchmarking."""
        project_dir = Path(tempfile.mkdtemp())

        # Create multiple modules with many functions
        for i in range(10):
            module_content = f'''
"""Module {i} - Test module for benchmarking."""

class Class{i}:
    """Test class {i}."""
    
    def __init__(self):
        self.value = 0
    
    def method1(self, x):
        if x > 0:
            return self._process(x)
        return None
    
    def method2(self, x):
        for i in range(x):
            self.value += i
        return self.value
    
    def _process(self, x):
        return x * 2

class AnotherClass{i}:
    """Another test class."""
    
    def connect(self):
        self.state = "connected"
    
    def disconnect(self):
        self.state = "disconnected"

def standalone_func_{i}(data):
    """Process data."""
    if not data:
        return []
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result

def helper_{i}(x):
    return x + 1
'''
            (project_dir / f"module_{i}.py").write_text(module_content)

        yield project_dir

        shutil.rmtree(project_dir)

    def test_fast_mode_performance(self, large_project):
        """Benchmark fast mode analysis."""
        analyzer = ProjectAnalyzer(FAST_CONFIG)

        start = time.time()
        result = analyzer.analyze_project(str(large_project))
        elapsed = time.time() - start

        # Fast mode should complete in reasonable time
        assert elapsed < 30.0, f"Analysis took too long: {elapsed:.2f}s"

        # Should find functions
        assert result.get_function_count() > 0

        print(f"\nFast mode: {elapsed:.2f}s, {result.get_function_count()} functions")

    def test_caching_performance(self, large_project):
        """Benchmark caching improvement."""
        config = FAST_CONFIG
        config.performance.enable_cache = True
        config.performance.cache_dir = str(large_project / ".cache")

        # First run - cold cache
        analyzer1 = ProjectAnalyzer(config)
        start = time.time()
        result1 = analyzer1.analyze_project(str(large_project))
        cold_time = time.time() - start

        # Second run - warm cache
        analyzer2 = ProjectAnalyzer(config)
        start = time.time()
        result2 = analyzer2.analyze_project(str(large_project))
        warm_time = time.time() - start

        # Warm cache should be faster
        speedup = cold_time / warm_time if warm_time > 0 else 1.0
        print(
            f"\nCache speedup: {speedup:.2f}x (cold: {cold_time:.2f}s, warm: {warm_time:.2f}s)"
        )

        assert result2.stats.get("cache_hits", 0) > 0

    def test_parallel_vs_sequential(self, large_project):
        """Compare parallel vs sequential performance."""
        # Sequential
        config_seq = FAST_CONFIG
        config_seq.performance.parallel_enabled = False

        analyzer_seq = ProjectAnalyzer(config_seq)
        start = time.time()
        result_seq = analyzer_seq.analyze_project(str(large_project))
        seq_time = time.time() - start

        # Parallel
        config_par = FAST_CONFIG
        config_par.performance.parallel_enabled = True
        config_par.performance.parallel_workers = 4

        analyzer_par = ProjectAnalyzer(config_par)
        start = time.time()
        result_par = analyzer_par.analyze_project(str(large_project))
        par_time = time.time() - start

        speedup = seq_time / par_time if par_time > 0 else 1.0
        print(
            f"\nParallel speedup: {speedup:.2f}x (seq: {seq_time:.2f}s, par: {par_time:.2f}s)"
        )

    def test_scaling_with_project_size(self, tmp_path):
        """Test how analysis scales with project size."""
        sizes = [5, 10, 20]  # Number of modules
        results = []

        for size in sizes:
            # Create project
            project_dir = tmp_path / f"project_{size}"
            project_dir.mkdir()

            for i in range(size):
                (project_dir / f"mod_{i}.py").write_text(f"""
def func_a_{i}(x): return x + 1
def func_b_{i}(x): return x * 2
def func_c_{i}(x): return func_a_{i}(func_b_{i}(x))
""")

            # Analyze
            analyzer = ProjectAnalyzer(FAST_CONFIG)
            start = time.time()
            result = analyzer.analyze_project(str(project_dir))
            elapsed = time.time() - start

            results.append(
                {
                    "size": size,
                    "functions": result.get_function_count(),
                    "time": elapsed,
                    "nodes": result.get_node_count(),
                }
            )

            shutil.rmtree(project_dir)

        print("\nScaling results:")
        for r in results:
            print(
                f"  {r['size']} modules: {r['time']:.2f}s, {r['functions']} funcs, {r['nodes']} nodes"
            )

        # Time should scale roughly linearly
        if len(results) >= 2:
            ratio = results[-1]["time"] / results[0]["time"]
            size_ratio = results[-1]["size"] / results[0]["size"]
            # Allow up to 3x overhead
            assert ratio < size_ratio * 3, (
                f"Scaling worse than linear: {ratio:.2f}x for {size_ratio:.0f}x size"
            )


class TestMemoryBenchmarks:
    """Memory usage benchmarks."""

    def test_memory_usage_stays_bounded(self, tmp_path):
        """Test that memory usage stays within bounds."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_mem = process.memory_info().rss / 1024 / 1024  # MB

        # Create medium project
        project_dir = tmp_path / "medium_project"
        project_dir.mkdir()

        for i in range(20):
            (project_dir / f"mod_{i}.py").write_text(f"""
class Class{i}:
    def method1(self): pass
    def method2(self): pass
    def method3(self): pass
def func_{i}(): pass
""")

        # Analyze
        analyzer = ProjectAnalyzer(FAST_CONFIG)
        result = analyzer.analyze_project(str(project_dir))

        final_mem = process.memory_info().rss / 1024 / 1024  # MB
        mem_increase = final_mem - initial_mem

        print(f"\nMemory increase: {mem_increase:.1f} MB")
        print(f"  Functions: {result.get_function_count()}")
        print(f"  Nodes: {result.get_node_count()}")

        # Memory should be reasonable (< 500MB increase)
        assert mem_increase < 500, f"Memory usage too high: {mem_increase:.1f} MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
