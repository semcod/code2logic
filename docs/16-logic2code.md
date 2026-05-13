## Overview

`logic2code` is a companion package that generates source code from Code2Logic output files (YAML, Hybrid YAML, TOON). It reads the logical representation and produces working code scaffolds.

## Installation

The package is included with code2logic:

```bash
pip install code2logic
```

# Show what can be generated
python -m logic2code out/code2logic/project.c2l.yaml --summary

# Generate Python code
python -m logic2code out/code2logic/project.c2l.yaml -o out/logic2code/generated_code/

# Generate with stubs only (no implementations)
python -m logic2code out/code2logic/project.c2l.yaml -o out/logic2code/generated_code/ --stubs-only

# Generate specific modules
python -m logic2code out/code2logic/project.c2l.yaml -o out/logic2code/generated_code/ --modules "analyzer.py,parsers.py"
```

### Python API

```python
from logic2code import CodeGenerator, GeneratorConfig

# Create generator
generator = CodeGenerator('out/code2logic/project.c2l.yaml')

# Get summary
summary = generator.summary()
print(f"Modules: {summary['total_modules']}")
print(f"Classes: {summary['total_classes']}")

# Generate code
result = generator.generate('output/')
print(f"Generated {result.files_generated} files")

# Generate single module
code = generator.generate_module('analyzer.py')
print(code)
```

### Class Generation

Generates complete class structures:
- Class declarations with bases
- Method signatures with type hints
- Docstrings from intents
- Dataclass support with fields

```python
@dataclass
class ProjectInfo:
    """Information about analyzed project."""
    name: str
    total_files: int = 0
    total_lines: int = 0
    modules: List[ModuleInfo] = field(default_factory=list)
```

### Function Generation

Generates function scaffolds:
- Full signatures with parameters
- Type annotations
- Default values
- Async support
- Decorator preservation

```python
async def analyze_project(
    path: str,
    use_treesitter: bool = True,
    verbose: bool = False
) -> ProjectInfo:
    """Analyzes project and returns ProjectInfo."""
    raise NotImplementedError("TODO: Implement analyze_project")
```

### Import Generation

Automatically generates import statements:
- Standard library imports
- Third-party imports
- Local imports
- Type checking imports

## Configuration

```python
from logic2code import GeneratorConfig

config = GeneratorConfig(
    language='python',            # Target language
    stubs_only=False,            # Generate stubs only
    include_docstrings=True,     # Include docstrings
    include_type_hints=True,     # Include type annotations
    generate_init=True,          # Generate __init__.py files
    preserve_structure=True,     # Preserve directory structure
)

generator = CodeGenerator('project.c2l.yaml', config)
```

## CLI Reference

```
usage: logic2code [-h] [-o OUTPUT] [-l {python}] [--stubs-only]
                  [--modules MODULES] [--summary] [-v]
                  input

Generate code from Code2Logic output files

positional arguments:
  input                 Path to Code2Logic output file

optional arguments:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   Output directory for generated code
  -l, --language LANG   Target language (default: python)
  --stubs-only          Generate stubs only (no implementations)
  --modules MODULES     Comma-separated list of modules to generate
  --summary             Show summary without generating
  -v, --verbose         Verbose output
```

# 1. Analyze original code
code2logic src/ -f yaml -o out/code2logic/project.c2l.yaml

# 3. Generate new code from modified logic
python -m logic2code out/code2logic/project.c2l.yaml -o out/logic2code/new_src/

# 4. Compare and merge
diff -r src/ out/logic2code/new_src/
```

### Refactoring Workflow

1. Generate logic from existing code
2. Modify the logic representation
3. Generate new code structure
4. Manually migrate implementation details

## Best Practices

1. **Use stubs first** - Generate with `--stubs-only` for initial scaffolds
2. **Review signatures** - Verify type hints and defaults
3. **Add implementations** - Replace `NotImplementedError` with actual code
4. **Run tests** - Use logic2test to generate matching tests
