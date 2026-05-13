## Overview

`logic2test` is a companion package that generates test files from Code2Logic output files (YAML, Hybrid YAML, TOON). It reads the logical representation of your codebase and produces pytest-compatible test scaffolds.

## Installation

The package is included with code2logic:

```bash
pip install code2logic
```

# Show what can be generated
python -m logic2test out/code2logic/project.c2l.yaml --summary

# Generate unit tests
python -m logic2test out/code2logic/project.c2l.yaml -o out/logic2test/tests/

# Generate all test types
python -m logic2test out/code2logic/project.c2l.hybrid.yaml -o out/logic2test/tests/ --type all

# Include private methods
python -m logic2test out/code2logic/project.c2l.yaml -o out/logic2test/tests/ --include-private
```

### Python API

```python
from logic2test import TestGenerator, GeneratorConfig

# Create generator
generator = TestGenerator('out/code2logic/project.c2l.yaml')

# Get summary
summary = generator.summary()
print(f"Classes: {summary['testable_classes']}")
print(f"Functions: {summary['testable_functions']}")

# Generate unit tests
result = generator.generate_unit_tests('out/logic2test/tests/')
print(f"Generated {result.tests_generated} tests")

# Generate integration tests
result = generator.generate_integration_tests('tests/integration/')

# Generate property-based tests (Hypothesis)
result = generator.generate_property_tests('tests/property/')
```

### Unit Tests

Generated for each class and function with:

- Arrange-Act-Assert structure
- Mocked parameters based on type hints
- Return type assertions
- TODO comments for implementation

```python
def test_analyze_project():
    """Test analyze_project function."""
    # Arrange
    path = "/tmp/test_path"
    use_treesitter = Mock()
    verbose = False

    # Act
    # result = analyze_project(path, use_treesitter, verbose)

    # Assert
    assert result is not None  # TODO: Add specific assertion
```

### Integration Tests

Focus on cross-module interactions:

- Tests for public classes
- Dependency injection patterns
- Module collaboration scenarios

### Property Tests

For dataclasses using Hypothesis:

- Serialization roundtrip tests
- Field validation tests
- Equality tests

## Configuration

```python
from logic2test import GeneratorConfig

config = GeneratorConfig(
    framework='pytest',           # or 'unittest'
    include_private=False,        # Include _private methods
    include_dunder=False,         # Include __dunder__ methods
    max_tests_per_file=50,
    output_prefix='test_',
    generate_class_tests=True,
    generate_function_tests=True,
    generate_dataclass_tests=True,
)

generator = TestGenerator('out/code2logic/project.c2l.yaml', config)
```

## CLI Reference

```text
usage: logic2test [-h] [-o OUTPUT] [-t {unit,integration,property,all}]
                  [--framework {pytest,unittest}] [--include-private]
                  [--include-dunder] [--summary] [-v]
                  input

Generate tests from Code2Logic output files

positional arguments:
  input                 Path to Code2Logic output file (YAML, Hybrid, or TOON)

optional arguments:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   Output directory for generated tests
  -t, --type TYPE       Type of tests to generate: unit, integration, property, all
  --framework FRAMEWORK Test framework: pytest or unittest
  --include-private     Include private methods/functions
  --include-dunder      Include dunder methods
  --summary             Show summary without generating
  -v, --verbose         Verbose output
```

## Supported Input Formats

| Format | Extension | Description |
| ------ | --------- | ----------- |
| YAML | `.yaml` | Standard Code2Logic YAML output |
| Hybrid | `.hybrid.yaml` | Compact YAML with full metadata |
| TOON | `.toon` | Token-Oriented Object Notation |

## Output Structure

```text
tests/
├── unit/
│   ├── test_analyzer.py
│   ├── test_parsers.py
│   └── test_generators.py
├── integration/
│   └── test_integration.py
└── property/
    └── test_properties.py
```

## Best Practices

1. **Review generated tests** - Tests are scaffolds, not complete implementations
2. **Uncomment imports** - Import statements are commented for safety
3. **Add assertions** - Replace TODO comments with real assertions
4. **Run with pytest** - `pytest tests/ -v`
