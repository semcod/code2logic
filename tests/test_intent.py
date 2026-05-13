"""
Tests for intent analysis functionality.
"""

from unittest.mock import Mock

from code2logic.intent import IntentAnalyzer, IntentType
from code2logic.models import ProjectInfo, ModuleInfo, FunctionInfo, ClassInfo


def make_function(name, params=None, complexity=1, lines=5, docstring=None):
    """Helper to create FunctionInfo with correct fields."""
    return FunctionInfo(
        name=name,
        params=params or [],
        return_type=None,
        docstring=docstring,
        calls=[],
        raises=[],
        complexity=complexity,
        lines=lines,
        decorators=[],
        is_async=False,
        is_static=False,
        is_private=False,
        intent="",
        start_line=1,
        end_line=lines,
    )


def make_class(name, methods=None, bases=None):
    """Helper to create ClassInfo with correct fields."""
    return ClassInfo(
        name=name,
        bases=bases or [],
        docstring=None,
        methods=methods or [],
        properties=[],
        is_interface=False,
        is_abstract=False,
        generic_params=[],
    )


def make_module(name, path, functions=None, classes=None, imports=None, lines_total=10):
    """Helper to create ModuleInfo with correct fields."""
    return ModuleInfo(
        path=path,
        language="python",
        imports=imports or [],
        exports=[],
        classes=classes or [],
        functions=functions or [],
        types=[],
        constants=[],
        docstring=None,
        lines_total=lines_total,
        lines_code=lines_total - 2,
    )


def make_project(name, modules):
    """Helper to create ProjectInfo with correct fields."""
    return ProjectInfo(
        name=name,
        root_path="/test",
        languages={"python": len(modules)},
        modules=modules,
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=len(modules),
        total_lines=sum(m.lines_total for m in modules),
        generated_at="2026-01-03T12:00:00Z",
    )


class TestIntentAnalyzer:
    """Test cases for IntentAnalyzer."""

    def test_init(self):
        """Test IntentAnalyzer initialization."""
        analyzer = IntentAnalyzer()

        assert analyzer.intent_patterns is not None
        assert analyzer.code_smell_patterns is not None
        assert IntentType.REFACTOR in analyzer.intent_patterns
        assert IntentType.ANALYZE in analyzer.intent_patterns

    def test_extract_keywords(self):
        """Test keyword extraction from queries."""
        analyzer = IntentAnalyzer()

        query = "I want to refactor the main module and improve performance"
        keywords = analyzer._extract_keywords(query)

        assert "want" in keywords
        assert "refactor" in keywords
        assert "main" in keywords
        assert "module" in keywords
        assert "improve" in keywords
        assert "performance" in keywords

    def test_calculate_intent_confidence(self):
        """Test intent confidence calculation."""
        analyzer = IntentAnalyzer()

        # Test with matching keywords
        keywords = ["refactor", "improve", "code"]
        patterns = ["refactor", "restructure", "improve", "clean"]

        confidence = analyzer._calculate_intent_confidence(keywords, patterns)
        assert confidence == 0.5  # 2 matches out of 4 patterns

        # Test with no matches
        keywords = ["test", "debug", "fix"]
        confidence = analyzer._calculate_intent_confidence(keywords, patterns)
        assert confidence == 0.0

    def test_identify_target_module(self, sample_project_model):
        """Test target identification for modules."""
        analyzer = IntentAnalyzer()

        query = "analyze the module1 module"
        target = analyzer._identify_target(query, sample_project_model)

        assert target == "module1"

    def test_identify_target_function(self, sample_project_model):
        """Test target identification for functions."""
        analyzer = IntentAnalyzer()

        # Add a function to the project
        func = make_function("test_func")
        sample_project_model.modules[0].functions.append(func)

        # Query must contain module name for target identification
        query = "refactor the test_func function in module1"
        target = analyzer._identify_target(query, sample_project_model)

        assert target == "module1.test_func"

    def test_identify_target_class(self, sample_project_model):
        """Test target identification for classes."""
        analyzer = IntentAnalyzer()

        # Add a class to the project
        cls = make_class("TestClass")
        sample_project_model.modules[0].classes.append(cls)

        # Query must contain module name for target identification
        query = "improve the TestClass class in module1"
        target = analyzer._identify_target(query, sample_project_model)

        assert target == "module1.TestClass"

    def test_identify_target_project(self, sample_project_model):
        """Test target identification for project-level queries."""
        analyzer = IntentAnalyzer()

        query = "analyze the entire project"
        target = analyzer._identify_target(query, sample_project_model)

        assert target == "project"

    def test_generate_description(self):
        """Test description generation for intents."""
        analyzer = IntentAnalyzer()

        description = analyzer._generate_description(IntentType.REFACTOR, "module1")
        assert "Refactoring suggestions for module1" in description

        description = analyzer._generate_description(IntentType.ANALYZE, "TestClass")
        assert "Analysis of TestClass" in description

    def test_generate_suggestions_refactor(self):
        """Test suggestion generation for refactor intent."""
        analyzer = IntentAnalyzer()

        suggestions = analyzer._generate_suggestions(
            IntentType.REFACTOR, "module1", Mock()
        )
        assert len(suggestions) > 0
        assert any("dependency" in s.lower() for s in suggestions)

    def test_generate_suggestions_analyze(self):
        """Test suggestion generation for analyze intent."""
        analyzer = IntentAnalyzer()

        suggestions = analyzer._generate_suggestions(
            IntentType.ANALYZE, "module1", Mock()
        )
        assert len(suggestions) > 0
        assert any("dependency" in s.lower() for s in suggestions)

    def test_generate_suggestions_optimize(self):
        """Test suggestion generation for optimize intent."""
        analyzer = IntentAnalyzer()

        suggestions = analyzer._generate_suggestions(
            IntentType.OPTIMIZE, "module1", Mock()
        )
        assert len(suggestions) > 0
        assert any("performance" in s.lower() for s in suggestions)

    def test_analyze_intent_refactor(self, sample_project_model):
        """Test intent analysis for refactoring."""
        analyzer = IntentAnalyzer()

        query = "I want to refactor the main module to improve code quality"
        intents = analyzer.analyze_intent(query, sample_project_model)

        assert len(intents) > 0

        # Check that refactor intent is detected
        refactor_intents = [i for i in intents if i.type == IntentType.REFACTOR]
        assert len(refactor_intents) > 0

        refactor_intent = refactor_intents[0]
        assert refactor_intent.confidence > 0.3
        assert "refactor" in refactor_intent.description.lower()
        assert len(refactor_intent.suggestions) > 0

    def test_analyze_intent_analyze(self, sample_project_model):
        """Test intent analysis for analysis."""
        analyzer = IntentAnalyzer()

        query = "Please analyze this project and explain the structure"
        intents = analyzer.analyze_intent(query, sample_project_model)

        assert len(intents) > 0

        # Check that analyze intent is detected
        analyze_intents = [i for i in intents if i.type == IntentType.ANALYZE]
        assert len(analyze_intents) > 0

    def test_analyze_intent_optimize(self, sample_project_model):
        """Test intent analysis for optimization."""
        analyzer = IntentAnalyzer()

        query = "How can I optimize the performance of this code?"
        intents = analyzer.analyze_intent(query, sample_project_model)

        assert len(intents) > 0

        # Check that optimize intent is detected
        optimize_intents = [i for i in intents if i.type == IntentType.OPTIMIZE]
        assert len(optimize_intents) > 0

    def test_analyze_intent_multiple(self, sample_project_model):
        """Test intent analysis with multiple possible intents."""
        analyzer = IntentAnalyzer()

        query = "I want to analyze and refactor the module to improve performance"
        intents = analyzer.analyze_intent(query, sample_project_model)

        assert len(intents) > 1  # Should detect multiple intents

        # Check that different intent types are detected
        intent_types = {i.type for i in intents}
        assert IntentType.ANALYZE in intent_types
        assert IntentType.REFACTOR in intent_types
        assert IntentType.OPTIMIZE in intent_types

    def test_analyze_intent_sorting(self, sample_project_model):
        """Test that intents are sorted by confidence."""
        analyzer = IntentAnalyzer()

        query = "refactor improve optimize analyze"
        intents = analyzer.analyze_intent(query, sample_project_model)

        assert len(intents) > 1

        # Check that intents are sorted by confidence (descending)
        for i in range(len(intents) - 1):
            assert intents[i].confidence >= intents[i + 1].confidence

    def test_detect_code_smells_long_module(self):
        """Test code smell detection for long modules."""
        analyzer = IntentAnalyzer()

        # Create a long module
        long_module = make_module(
            name="long_module",
            path="/test/long_module.py",
            lines_total=600,  # Over threshold
        )

        project = make_project("test", [long_module])

        smells = analyzer.detect_code_smells(project)

        long_module_smells = [s for s in smells if s["target"] == "long_module"]
        assert len(long_module_smells) > 0
        assert any(s["type"] == "long_module" for s in long_module_smells)

    def test_detect_code_smells_complex_function(self):
        """Test code smell detection for complex functions."""
        analyzer = IntentAnalyzer()

        # Create a complex function
        complex_func = make_function(
            "complex_func", params=["arg1", "arg2"], complexity=15, lines=20
        )

        module = make_module(
            name="test_module",
            path="/test/test_module.py",
            functions=[complex_func],
            lines_total=25,
        )

        project = make_project("test", [module])

        smells = analyzer.detect_code_smells(project)

        complex_func_smells = [s for s in smells if "complex_func" in s["target"]]
        assert len(complex_func_smells) > 0
        assert any(s["type"] == "complex_function" for s in complex_func_smells)

    def test_detect_code_smells_large_class(self):
        """Test code smell detection for large classes."""
        analyzer = IntentAnalyzer()

        # Create a large class with many methods
        many_methods = [make_function(f"method_{i}") for i in range(20)]
        large_class = make_class("LargeClass", methods=many_methods)

        module = make_module(
            name="test_module",
            path="/test/test_module.py",
            classes=[large_class],
            lines_total=105,
        )

        project = make_project("test", [module])

        smells = analyzer.detect_code_smells(project)

        large_class_smells = [s for s in smells if "LargeClass" in s["target"]]
        assert len(large_class_smells) > 0
        assert any(s["type"] == "large_class" for s in large_class_smells)

    def test_detect_code_smells_too_many_imports(self):
        """Test code smell detection for too many imports."""
        analyzer = IntentAnalyzer()

        # Create module with many imports
        many_imports = [f"module_{i}" for i in range(25)]  # Over threshold

        module = make_module(
            name="import_heavy_module",
            path="/test/import_heavy_module.py",
            imports=many_imports,
            lines_total=10,
        )

        project = make_project("test", [module])

        smells = analyzer.detect_code_smells(project)

        import_smells = [s for s in smells if s["target"] == "import_heavy_module"]
        assert len(import_smells) > 0
        assert any(s["type"] == "too_many_imports" for s in import_smells)

    def test_suggest_refactoring_module(self, sample_project_model):
        """Test refactoring suggestions for modules."""
        analyzer = IntentAnalyzer()

        # Add many functions to trigger suggestions
        many_functions = [make_function(f"func_{i}") for i in range(25)]
        sample_project_model.modules[0].functions.extend(many_functions)

        suggestions = analyzer.suggest_refactoring("module1", sample_project_model)

        assert len(suggestions) > 0
        assert any("split" in s.lower() for s in suggestions)

    def test_suggest_refactoring_class(self, sample_project_model):
        """Test refactoring suggestions for classes."""
        analyzer = IntentAnalyzer()

        # Add a large class
        many_methods = [make_function(f"method_{i}") for i in range(20)]
        large_class = make_class("LargeClass", methods=many_methods)
        sample_project_model.modules[0].classes.append(large_class)

        suggestions = analyzer.suggest_refactoring(
            "module1.LargeClass", sample_project_model
        )

        assert len(suggestions) > 0
        assert any("split" in s.lower() or "smaller" in s.lower() for s in suggestions)

    def test_suggest_refactoring_function(self, sample_project_model):
        """Test refactoring suggestions for functions."""
        analyzer = IntentAnalyzer()

        # Add a complex function
        complex_func = make_function(
            "complex_func",
            params=["arg1", "arg2"],
            complexity=12,
            lines=60,
            docstring=None,
        )
        sample_project_model.modules[0].functions.append(complex_func)

        suggestions = analyzer.suggest_refactoring(
            "module1.complex_func", sample_project_model
        )

        assert len(suggestions) > 0
        assert any("break" in s.lower() for s in suggestions)
        assert any("docstring" in s.lower() for s in suggestions)

    def test_find_target_object_module(self, sample_project_model):
        """Test finding target object for module."""
        analyzer = IntentAnalyzer()

        target = analyzer._find_target_object("module1", sample_project_model)

        assert target is not None
        # Module path contains module1
        assert "module1" in target.path
        assert isinstance(target, ModuleInfo)

    def test_find_target_object_function(self, sample_project_model):
        """Test finding target object for function."""
        analyzer = IntentAnalyzer()

        # Add a function
        func = make_function("test_func")
        sample_project_model.modules[0].functions.append(func)

        target = analyzer._find_target_object("module1.test_func", sample_project_model)

        assert target is not None
        assert target.name == "test_func"
        assert isinstance(target, FunctionInfo)

    def test_find_target_object_class(self, sample_project_model):
        """Test finding target object for class."""
        analyzer = IntentAnalyzer()

        # Add a class
        cls = make_class("TestClass")
        sample_project_model.modules[0].classes.append(cls)

        target = analyzer._find_target_object("module1.TestClass", sample_project_model)

        assert target is not None
        assert target.name == "TestClass"
        assert isinstance(target, ClassInfo)

    def test_find_target_object_not_found(self, sample_project_model):
        """Test finding non-existent target object."""
        analyzer = IntentAnalyzer()

        target = analyzer._find_target_object("nonexistent", sample_project_model)

        assert target is None

    def test_suggest_module_refactoring(self):
        """Test module-specific refactoring suggestions."""
        analyzer = IntentAnalyzer()

        # Module with many functions
        many_functions = [make_function(f"func_{i}") for i in range(25)]
        module = make_module(
            name="complex_module",
            path="/test/complex_module.py",
            functions=many_functions,
            lines_total=150,
        )

        suggestions = analyzer._suggest_module_refactoring(module)

        assert len(suggestions) > 0
        assert any("split" in s.lower() for s in suggestions)

    def test_suggest_class_refactoring(self):
        """Test class-specific refactoring suggestions."""
        analyzer = IntentAnalyzer()

        # Class with many methods and base classes
        many_methods = [make_function(f"method_{i}") for i in range(20)]
        cls = make_class(
            name="ComplexClass",
            methods=many_methods,
            bases=["Base1", "Base2", "Base3", "Base4"],  # Many base classes
        )

        suggestions = analyzer._suggest_class_refactoring(cls)

        assert len(suggestions) > 0
        assert any("split" in s.lower() for s in suggestions)
        assert any("composition" in s.lower() for s in suggestions)

    def test_suggest_function_refactoring(self):
        """Test function-specific refactoring suggestions."""
        analyzer = IntentAnalyzer()

        # Complex function with many parameters
        func = make_function(
            name="complex_func",
            params=[f"param_{i}" for i in range(7)],  # Many parameters
            lines=60,
            complexity=12,
            docstring=None,
        )

        suggestions = analyzer._suggest_function_refactoring(func)

        assert len(suggestions) > 0
        assert any("break" in s.lower() for s in suggestions)
        assert any("parameter" in s.lower() for s in suggestions)
        assert any("docstring" in s.lower() for s in suggestions)
