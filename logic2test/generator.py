"""
Main test generator that orchestrates parsing and test generation.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from .parsers import ClassSpec, FunctionSpec, LogicParser, ModuleSpec, ProjectSpec
from .templates import TestTemplate


@dataclass
class GeneratorConfig:
    """Configuration for test generation."""

    framework: str = "pytest"
    include_private: bool = False
    include_dunder: bool = False
    max_tests_per_file: int = 50
    output_prefix: str = "test_"
    generate_class_tests: bool = True
    generate_function_tests: bool = True
    generate_dataclass_tests: bool = True
    add_type_hints: bool = True


@dataclass
class GenerationResult:
    """Result of test generation."""

    files_generated: int = 0
    tests_generated: int = 0
    classes_covered: int = 0
    functions_covered: int = 0
    output_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class TestGenerator:
    """
    Main test generator class.

    Reads Code2Logic output files and generates test files.

    Usage:
        generator = TestGenerator('project.c2l.yaml')
        result = generator.generate_unit_tests('tests/')
        print(f"Generated {result.tests_generated} tests")
    """

    def __init__(self, logic_file: Union[str, Path], config: Optional[GeneratorConfig] = None):
        """
        Initialize test generator.

        Args:
            logic_file: Path to Code2Logic output file (YAML, Hybrid, or TOON)
            config: Optional configuration for generation
        """
        self.logic_file = Path(logic_file)
        self.config = config or GeneratorConfig()
        self.template = TestTemplate(name="default", framework=self.config.framework)
        self._project: Optional[ProjectSpec] = None

    @property
    def project(self) -> ProjectSpec:
        """Lazy-load and cache project spec."""
        if self._project is None:
            parser = LogicParser(self.logic_file)
            self._project = parser.parse()
        return self._project

    def generate_unit_tests(
        self, output_dir: Union[str, Path], modules: Optional[List[str]] = None
    ) -> GenerationResult:
        """
        Generate unit tests for the project.

        Args:
            output_dir: Directory to write test files
            modules: Optional list of module paths to generate tests for
                    (None = all modules)

        Returns:
            GenerationResult with statistics
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        result = GenerationResult()

        for module in self.project.modules:
            # Filter modules if specified
            if modules and module.path not in modules:
                continue

            # Skip non-Python modules for now
            if module.language != "python":
                continue

            try:
                test_content, stats = self._generate_module_tests(module)

                if test_content.strip():
                    # Generate output filename
                    test_filename = self._get_test_filename(module.path)
                    test_file = output_path / test_filename

                    test_file.write_text(test_content, encoding="utf-8")

                    result.files_generated += 1
                    result.tests_generated += stats["tests"]
                    result.classes_covered += stats["classes"]
                    result.functions_covered += stats["functions"]
                    result.output_files.append(str(test_file))

            except Exception as e:
                result.errors.append(f"Error processing {module.path}: {e}")

        return result

    def _generate_module_tests(self, module: ModuleSpec) -> tuple:
        """Generate tests for a single module."""
        parts = []
        stats = {"tests": 0, "classes": 0, "functions": 0}

        # File header
        parts.append(self.template.render_test_file_header(module.path, module.imports))

        # Class tests
        if self.config.generate_class_tests:
            for cls in module.classes:
                if self._should_test_class(cls):
                    class_tests = self._generate_class_tests(cls)
                    parts.append(class_tests)
                    stats["classes"] += 1
                    stats["tests"] += class_tests.count("def test_")

        # Standalone function tests
        if self.config.generate_function_tests:
            for func in module.functions:
                if self._should_test_function(func):
                    func_test = self.template.render_function_test(
                        func_name=func.name,
                        params=func.params,
                        return_type=func.return_type,
                        docstring=func.docstring,
                        is_async=func.is_async,
                    )
                    parts.append(func_test)
                    stats["functions"] += 1
                    stats["tests"] += 1

        return "\n".join(parts), stats

    def _generate_class_tests(self, cls: ClassSpec) -> str:
        """Generate tests for a class and its methods."""
        parts = []

        # Class instantiation test
        class_test = self.template.render_class_test(
            class_name=cls.name,
            bases=cls.bases,
            is_dataclass=cls.is_dataclass,
            fields=cls.fields,
            docstring=cls.docstring,
        )
        parts.append(class_test)

        # Dataclass-specific tests
        if cls.is_dataclass and cls.fields and self.config.generate_dataclass_tests:
            dc_test = self.template.render_dataclass_test(class_name=cls.name, fields=cls.fields)
            parts.append(dc_test)

        # Method tests
        for method in cls.methods:
            if self._should_test_function(method):
                method_test = self.template.render_function_test(
                    func_name=method.name,
                    params=method.params,
                    return_type=method.return_type,
                    docstring=method.docstring,
                    is_async=method.is_async,
                    class_name=cls.name,
                )
                parts.append(method_test)

        return "\n".join(parts)

    def _should_test_class(self, cls: ClassSpec) -> bool:
        """Determine if a class should have tests generated."""
        name = cls.name

        # Skip private classes unless configured
        if name.startswith("_") and not self.config.include_private:
            return False

        # Skip test classes
        if name.startswith("Test") or name.endswith("Test"):
            return False

        # Skip mixin/helper classes (heuristic)
        if name.endswith("Mixin") or name.endswith("Helper"):
            return False

        return True

    def _should_test_function(self, func: FunctionSpec) -> bool:
        """Determine if a function should have tests generated."""
        name = func.name

        # Skip private functions unless configured
        if name.startswith("_") and not name.startswith("__"):
            if not self.config.include_private:
                return False

        # Skip dunder methods unless configured
        if name.startswith("__") and name.endswith("__"):
            if not self.config.include_dunder:
                # But always test __init__ for classes
                if name not in ("__init__", "__new__", "__call__"):
                    return False

        # Skip test functions
        if name.startswith("test_"):
            return False

        return True

    def _get_test_filename(self, module_path: str) -> str:
        """Generate test filename from module path."""
        # Extract filename from path
        path = Path(module_path)
        name = path.stem

        # Clean up name
        name = re.sub(r"[^\w]", "_", name)

        # Add test prefix
        if not name.startswith("test_"):
            name = f"{self.config.output_prefix}{name}"

        return f"{name}.py"

    def generate_integration_tests(
        self, output_dir: Union[str, Path], entry_points: Optional[List[str]] = None
    ) -> GenerationResult:
        """
        Generate integration tests focusing on module interactions.

        Args:
            output_dir: Directory to write test files
            entry_points: Optional list of entry point functions/classes

        Returns:
            GenerationResult with statistics
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        result = GenerationResult()

        # Generate a single integration test file
        lines = [
            '"""',
            "Integration tests for the project.",
            "",
            "Generated by logic2test from Code2Logic output.",
            '"""',
            "",
            "import pytest",
            "from unittest.mock import Mock, patch",
            "",
            "",
        ]

        # Find potential integration points
        public_classes = []
        public_functions = []

        for module in self.project.modules:
            for cls in module.classes:
                if not cls.name.startswith("_"):
                    public_classes.append((module.path, cls))
            for func in module.functions:
                if not func.name.startswith("_"):
                    public_functions.append((module.path, func))

        # Generate integration test class
        lines.append("class TestIntegration:")
        lines.append('    """Integration tests for cross-module functionality."""')
        lines.append("")

        # Test for each major class
        for module_path, cls in public_classes[:10]:
            lines.append(f"    def test_{cls.name.lower()}_integration(self):")
            lines.append(f'        """Test {cls.name} integration with dependencies."""')
            lines.append(f"        # TODO: Test {cls.name} with its dependencies")
            lines.append(f"        # Module: {module_path}")
            lines.append("        pass")
            lines.append("")
            result.tests_generated += 1

        lines.append("")

        content = "\n".join(lines)

        test_file = output_path / "test_integration.py"
        test_file.write_text(content, encoding="utf-8")

        result.files_generated = 1
        result.output_files.append(str(test_file))

        return result

    def generate_property_tests(self, output_dir: Union[str, Path]) -> GenerationResult:
        """
        Generate property-based tests using Hypothesis.

        Args:
            output_dir: Directory to write test files

        Returns:
            GenerationResult with statistics
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        result = GenerationResult()

        lines = [
            '"""',
            "Property-based tests using Hypothesis.",
            "",
            "Generated by logic2test from Code2Logic output.",
            '"""',
            "",
            "import pytest",
            "",
            "try:",
            "    from hypothesis import given, strategies as st",
            "    HAS_HYPOTHESIS = True",
            "except ImportError:",
            "    HAS_HYPOTHESIS = False",
            "",
            "",
            '@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="Hypothesis not installed")',
            "class TestProperties:",
            '    """Property-based tests for data structures."""',
            "",
        ]

        # Find dataclasses and generate property tests
        for module in self.project.modules:
            for cls in module.classes:
                if cls.is_dataclass and cls.fields:
                    lines.append(f"    # Property tests for {cls.name}")
                    lines.append("    # @given(...)")
                    lines.append(f"    def test_{cls.name.lower()}_roundtrip(self):")
                    lines.append(f'        """Test {cls.name} serialization roundtrip."""')
                    lines.append("        # TODO: Implement property test")
                    lines.append("        pass")
                    lines.append("")
                    result.tests_generated += 1

        if result.tests_generated == 0:
            lines.append("    def test_placeholder(self):")
            lines.append('        """Placeholder - no dataclasses found."""')
            lines.append("        pass")
            lines.append("")

        content = "\n".join(lines)

        test_file = output_path / "test_properties.py"
        test_file.write_text(content, encoding="utf-8")

        result.files_generated = 1
        result.output_files.append(str(test_file))

        return result

    def summary(self) -> Dict:
        """Get summary of what can be generated."""
        total_classes = 0
        total_functions = 0
        total_methods = 0
        testable_classes = 0
        testable_functions = 0
        dataclasses_count = 0

        for module in self.project.modules:
            for cls in module.classes:
                total_classes += 1
                if self._should_test_class(cls):
                    testable_classes += 1
                if cls.is_dataclass:
                    dataclasses_count += 1
                total_methods += len(cls.methods)

            for func in module.functions:
                total_functions += 1
                if self._should_test_function(func):
                    testable_functions += 1

        return {
            "project_name": self.project.name,
            "total_modules": len(self.project.modules),
            "total_classes": total_classes,
            "total_functions": total_functions,
            "total_methods": total_methods,
            "testable_classes": testable_classes,
            "testable_functions": testable_functions,
            "dataclasses": dataclasses_count,
        }
