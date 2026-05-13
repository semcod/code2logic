#!/usr/bin/env python3
"""
Test script for the Advanced Flow Analyzer
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flow import ProjectFlowAnalyzer


def create_sample_project():
    """Create a sample project for testing."""
    project_dir = tempfile.mkdtemp(prefix="test_project_")

    # Sample module 1: Simple functions
    module1 = '''
def process_data(data):
    """Process input data."""
    if not data:
        return None
    
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    
    return result

def validate_data(data):
    """Validate input data."""
    return isinstance(data, list) and all(isinstance(x, int) for x in data)
'''

    # Sample module 2: Class with state machine
    module2 = '''
class ConnectionState:
    """State machine for connection states."""
    
    def __init__(self):
        self.state = "disconnected"
        self.retry_count = 0
    
    def connect(self):
        """Transition to connecting state."""
        if self.state == "disconnected":
            self.state = "connecting"
            return True
        return False
    
    def connected(self):
        """Transition to connected state."""
        if self.state == "connecting":
            self.state = "connected"
            self.retry_count = 0
            return True
        return False
    
    def disconnect(self):
        """Transition to disconnected state."""
        self.state = "disconnected"
        return True
    
    def failed(self):
        """Handle connection failure."""
        if self.state == "connecting":
            self.retry_count += 1
            if self.retry_count > 3:
                self.state = "disconnected"
                self.retry_count = 0
            return True
        return False
'''

    # Sample module 3: Recursive functions
    module3 = '''
def factorial(n):
    """Calculate factorial recursively."""
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n):
    """Calculate Fibonacci number recursively."""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

def tree_traversal(node):
    """Traverse tree structure."""
    if not node:
        return []
    
    result = [node.value]
    result.extend(tree_traversal(node.left))
    result.extend(tree_traversal(node.right))
    return result
'''

    # Sample test file
    test_file = '''
import unittest
import sys
import os

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module1 import process_data, validate_data
from module2 import ConnectionState
from module3 import factorial

class TestProject(unittest.TestCase):
    
    def test_process_data(self):
        """Test data processing."""
        self.assertEqual(process_data([1, 2, 3]), [2, 4, 6])
        self.assertIsNone(process_data([]))
    
    def test_validate_data(self):
        """Test data validation."""
        self.assertTrue(validate_data([1, 2, 3]))
        self.assertFalse(validate_data("not a list"))
    
    def test_connection_state(self):
        """Test state machine."""
        conn = ConnectionState()
        self.assertEqual(conn.state, "disconnected")
        
        conn.connect()
        self.assertEqual(conn.state, "connecting")
        
        conn.connected()
        self.assertEqual(conn.state, "connected")
    
    def test_factorial(self):
        """Test recursive factorial."""
        self.assertEqual(factorial(5), 120)
        self.assertEqual(factorial(0), 1)

if __name__ == "__main__":
    unittest.main()
'''

    # Write files
    Path(project_dir, "module1.py").write_text(module1)
    Path(project_dir, "module2.py").write_text(module2)
    Path(project_dir, "module3.py").write_text(module3)
    Path(project_dir, "tests").mkdir()
    Path(project_dir, "tests", "test_project.py").write_text(test_file)

    return project_dir


def test_static_analysis():
    """Test static analysis functionality."""
    print("\n=== Testing Static Analysis ===")

    project_dir = create_sample_project()

    try:
        analyzer = ProjectFlowAnalyzer(mode="static")
        analyzer.analyze_project(project_dir, "test_output_static")

        # Check outputs
        assert os.path.exists("test_output_static/system_analysis.yaml")
        assert os.path.exists("test_output_static/analysis_report.md")

        print("✓ Static analysis test passed")

    except Exception as e:
        print(f"✗ Static analysis test failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        shutil.rmtree(project_dir)
        if os.path.exists("test_output_static"):
            shutil.rmtree("test_output_static")


def test_pattern_extraction():
    """Test behavioral pattern extraction."""
    print("\n=== Testing Pattern Extraction ===")

    project_dir = create_sample_project()

    try:
        analyzer = ProjectFlowAnalyzer(mode="behavioral")
        analyzer.analyze_project(project_dir, "test_output_patterns")

        # Check if patterns were detected
        assert len(analyzer.patterns) > 0

        # Check for specific patterns
        pattern_types = [p.type for p in analyzer.patterns]
        assert "sequential" in pattern_types
        assert "recursive" in pattern_types
        assert "state_machine" in pattern_types

        print(f"✓ Detected {len(analyzer.patterns)} patterns:")
        for p in analyzer.patterns:
            print(f"  - {p.name} ({p.type}, confidence: {p.confidence:.2f})")

    except Exception as e:
        print(f"✗ Pattern extraction test failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        shutil.rmtree(project_dir)
        if os.path.exists("test_output_patterns"):
            shutil.rmtree("test_output_patterns")


def test_hybrid_analysis():
    """Test hybrid static + dynamic analysis."""
    print("\n=== Testing Hybrid Analysis ===")

    project_dir = create_sample_project()

    try:
        analyzer = ProjectFlowAnalyzer(mode="hybrid")
        analyzer.analyze_project(project_dir, "test_output_hybrid")

        # Check all outputs
        outputs = [
            "system_analysis.yaml",
            "system_flow.mmd",
            "system_flow.png",
            "diagram_data.json",
            "analysis_report.md",
        ]

        for output in outputs:
            assert os.path.exists(f"test_output_hybrid/{output}")

        print("✓ Hybrid analysis test passed")
        print("Generated files:")
        for output in outputs:
            size = os.path.getsize(f"test_output_hybrid/{output}")
            print(f"  - {output} ({size} bytes)")

    except Exception as e:
        print(f"✗ Hybrid analysis test failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        shutil.rmtree(project_dir)
        if os.path.exists("test_output_hybrid"):
            shutil.rmtree("test_output_hybrid")


def test_llm_prompt_generation():
    """Test LLM prompt generation."""
    print("\n=== Testing LLM Prompt Generation ===")

    project_dir = create_sample_project()

    try:
        analyzer = ProjectFlowAnalyzer(mode="reverse")
        analyzer.analyze_project(project_dir, "test_output_llm")

        # Read generated prompt
        with open("test_output_llm/system_analysis_prompt.md", "r") as f:
            prompt = f.read()

        # Check prompt structure
        required_sections = [
            "# System Behavioral Analysis",
            "## Overview",
            "## Call Graph Structure",
            "## Behavioral Patterns",
            "## Data Flow Insights",
            "## Reverse Engineering Guidelines",
        ]

        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"

        print("✓ LLM prompt generation test passed")
        print(f"Prompt length: {len(prompt)} characters")

    except Exception as e:
        print(f"✗ LLM prompt test failed: {e}")
        import traceback

        traceback.print_exc()

    finally:
        shutil.rmtree(project_dir)
        if os.path.exists("test_output_llm"):
            shutil.rmtree("test_output_llm")


def main():
    """Run all tests."""
    print("Running Advanced Flow Analyzer Tests")
    print("=" * 50)

    # Check dependencies
    try:
        import networkx
        import matplotlib
        import numpy
        import yaml

        print("✓ All dependencies installed")
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return

    # Run tests
    test_static_analysis()
    test_pattern_extraction()
    test_hybrid_analysis()
    test_llm_prompt_generation()

    print("\n" + "=" * 50)
    print("Test suite complete!")


if __name__ == "__main__":
    main()
