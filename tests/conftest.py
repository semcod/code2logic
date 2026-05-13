"""
Pytest configuration and fixtures for code2logic tests.
"""

import pytest
import tempfile
from pathlib import Path

from code2logic.models import ProjectInfo, ModuleInfo, FunctionInfo, ClassInfo


@pytest.fixture
def sample_python_code() -> str:
    """Sample Python code for testing."""
    return '''
import os
import sys
from typing import List, Dict

def calculate_sum(numbers: List[int]) -> int:
    """Calculate the sum of a list of numbers."""
    total = 0
    for num in numbers:
        total += num
    return total

def fibonacci(n: int) -> int:
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

class Calculator:
    """A simple calculator class."""
    
    def __init__(self):
        self.history = []
    
    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def subtract(self, a: float, b: float) -> float:
        """Subtract two numbers."""
        result = a - b
        self.history.append(f"{a} - {b} = {result}")
        return result
    
    def get_history(self) -> List[str]:
        """Get calculation history."""
        return self.history.copy()
'''


@pytest.fixture
def sample_javascript_code() -> str:
    """Sample JavaScript code for testing."""
    return """
const os = require('os');
const fs = require('fs');

function calculateSum(numbers) {
    let total = 0;
    for (const num of numbers) {
        total += num;
    }
    return total;
}

function fibonacci(n) {
    if (n <= 1) {
        return n;
    }
    return fibonacci(n - 1) + fibonacci(n - 2);
}

class Calculator {
    constructor() {
        this.history = [];
    }
    
    add(a, b) {
        const result = a + b;
        this.history.push(`${a} + ${b} = ${result}`);
        return result;
    }
    
    subtract(a, b) {
        const result = a - b;
        this.history.push(`${a} - ${b} = ${result}`);
        return result;
    }
    
    getHistory() {
        return [...this.history];
    }
}

module.exports = { calculateSum, fibonacci, Calculator };
"""


@pytest.fixture
def sample_java_code() -> str:
    """Sample Java code for testing."""
    return """
import java.util.ArrayList;
import java.util.List;

public class Calculator {
    private List<String> history;
    
    public Calculator() {
        this.history = new ArrayList<>();
    }
    
    public double add(double a, double b) {
        double result = a + b;
        history.add(a + " + " + b + " = " + result);
        return result;
    }
    
    public double subtract(double a, double b) {
        double result = a - b;
        history.add(a + " - " + b + " = " + result);
        return result;
    }
    
    public List<String> getHistory() {
        return new ArrayList<>(history);
    }
    
    public static int fibonacci(int n) {
        if (n <= 1) {
            return n;
        }
        return fibonacci(n - 1) + fibonacci(n - 2);
    }
}
"""


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_project(temp_project_dir, sample_python_code):
    """Create a sample project with Python files."""
    # Create main module
    main_file = temp_project_dir / "main.py"
    main_file.write_text(sample_python_code)

    # Create utils module
    utils_file = temp_project_dir / "utils.py"
    utils_file.write_text('''
def helper_function():
    """A helper function."""
    return "helper"

class HelperClass:
    """A helper class."""
    
    def method(self):
        return "method result"
''')

    # Create __init__.py
    init_file = temp_project_dir / "__init__.py"
    init_file.write_text("")

    return temp_project_dir


@pytest.fixture
def sample_module():
    """Create a sample module for testing."""
    functions = [
        FunctionInfo(
            name="test_func",
            params=["arg1", "arg2"],
            return_type=None,
            docstring="Test function",
            calls=[],
            raises=[],
            complexity=2,
            lines=10,
            decorators=[],
            is_async=False,
            is_static=False,
            is_private=False,
            intent="Test function",
            start_line=1,
            end_line=10,
        )
    ]

    classes = [
        ClassInfo(
            name="TestClass",
            bases=[],
            docstring="Test class",
            methods=[
                FunctionInfo(
                    name="method1",
                    params=[],
                    return_type=None,
                    docstring="Method 1",
                    calls=[],
                    raises=[],
                    complexity=1,
                    lines=5,
                    decorators=[],
                    is_async=False,
                    is_static=False,
                    is_private=False,
                    intent="Method 1",
                    start_line=1,
                    end_line=5,
                )
            ],
            properties=[],
            is_interface=False,
            is_abstract=False,
            generic_params=[],
        )
    ]

    return ModuleInfo(
        path="/test/test_module.py",
        language="python",
        imports=["os", "sys"],
        exports=[],
        classes=classes,
        functions=functions,
        types=[],
        constants=[],
        docstring=None,
        lines_total=50,
        lines_code=40,
    )


@pytest.fixture
def sample_project_model():
    """Create a sample project model for testing."""
    module1 = ModuleInfo(
        path="/test/module1.py",
        language="python",
        imports=["os"],
        exports=[],
        classes=[],
        functions=[
            FunctionInfo(
                name="func1",
                params=[],
                return_type=None,
                docstring=None,
                calls=[],
                raises=[],
                complexity=1,
                lines=5,
                decorators=[],
                is_async=False,
                is_static=False,
                is_private=False,
                intent="",
                start_line=1,
                end_line=5,
            )
        ],
        types=[],
        constants=[],
        docstring=None,
        lines_total=10,
        lines_code=8,
    )

    module2 = ModuleInfo(
        path="/test/module2.py",
        language="python",
        imports=["sys", "module1"],
        exports=[],
        classes=[],
        functions=[
            FunctionInfo(
                name="func2",
                params=["arg"],
                return_type=None,
                docstring=None,
                calls=[],
                raises=[],
                complexity=2,
                lines=8,
                decorators=[],
                is_async=False,
                is_static=False,
                is_private=False,
                intent="",
                start_line=1,
                end_line=8,
            )
        ],
        types=[],
        constants=[],
        docstring=None,
        lines_total=15,
        lines_code=12,
    )

    return ProjectInfo(
        name="test_project",
        root_path="/test",
        languages={"python": 2},
        modules=[module1, module2],
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=2,
        total_lines=25,
        generated_at="2026-01-03T12:00:00Z",
    )


@pytest.fixture
def mock_llm_config():
    """Mock LLM configuration for testing."""
    return {
        "provider": "mock",
        "model": "test-model",
        "api_key": "test-key",
        "temperature": 0.7,
        "max_tokens": 1000,
    }


@pytest.fixture
def sample_analysis_result():
    """Sample analysis result for testing."""
    project = ProjectInfo(
        name="test_project",
        root_path="/test",
        languages={},
        modules=[],
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=0,
        total_lines=0,
        generated_at="2026-01-03T12:00:00Z",
    )

    return {
        "project": project,
        "analysis_time": 1.5,
        "parser_used": "tree_sitter",
        "errors": [],
        "warnings": ["Minor warning"],
    }
