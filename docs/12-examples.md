# Examples

> Usage examples and workflows for Code2Logic

[← README](../README.md) | [← LLM Integration](08-llm-integration.md) | [Architecture →](13-architecture.md)

## Available Examples

All examples are in the `examples/` folder:

- [examples/run_examples.sh](../examples/run_examples.sh) - Example runner script (multi-command workflows)
- [examples/code2logic/](../examples/code2logic/) - Minimal project + Docker example for code2logic
- [examples/logic2test/](../examples/logic2test/) - Minimal project + Docker example for logic2test
- [examples/logic2code/](../examples/logic2code/) - Minimal project + Docker example for logic2code

| Example | Description |
| --- | --- |
| [01_quick_start.py](../examples/01_quick_start.py) | Basic usage guide |
| [02_refactoring.py](../examples/02_refactoring.py) | Duplicate + quality analysis |
| [03_reproduction.py](../examples/03_reproduction.py) | Reproduce code from specs |
| [04_project.py](../examples/04_project.py) | Project-level reproduction |
| [05_llm_integration.py](../examples/05_llm_integration.py) | LLM integration demo |
| [06_metrics.py](../examples/06_metrics.py) | Detailed reproduction metrics |
| [08_format_benchmark.py](../examples/08_format_benchmark.py) | Benchmark formats across files |
| [09_async_benchmark.py](../examples/09_async_benchmark.py) | Parallel benchmark with multi-provider LLM |
| [10_function_reproduction.py](../examples/10_function_reproduction.py) | Function-level reproduction |
| [11_token_benchmark.py](../examples/11_token_benchmark.py) | Token-aware benchmark |
| [12_comprehensive_analysis.py](../examples/12_comprehensive_analysis.py) | Post-run analysis of generated outputs |
| [13_project_benchmark.py](../examples/13_project_benchmark.py) | Whole-project structure benchmark |
| [14_repeatability_test.py](../examples/14_repeatability_test.py) | Repeatability testing |
| [15_unified_benchmark.py](../examples/15_unified_benchmark.py) | Unified benchmark runner example |
| [16_terminal_demo.py](../examples/16_terminal_demo.py) | Terminal markdown rendering demo |

## Quick Start

```python
from code2logic import analyze_project

# Analyze a project
project = analyze_project("/path/to/project")

print(f"Files: {project.total_files}")
print(f"Lines: {project.total_lines}")
print(f"Languages: {list(project.languages.keys())}")
```

## BDD Workflow

Generate Gherkin specs and step definitions:

```python
from code2logic import analyze_project
from code2logic.gherkin import GherkinGenerator, StepDefinitionGenerator

# Analyze
project = analyze_project("./my_project")

# Generate Gherkin
gherkin_gen = GherkinGenerator()
gherkin = gherkin_gen.generate(project, detail='standard')

# Generate step definitions
step_gen = StepDefinitionGenerator()
steps = step_gen.generate(project)

# Save files
with open("features/project.feature", "w") as f:
    f.write(gherkin)

with open("tests/steps/test_steps.py", "w") as f:
    f.write(steps)
```

## Code Reproduction

Reproduce a single file (LLM optional):

```bash
# Show spec only
python examples/03_reproduction.py code2logic/models.py --show-spec

# Offline mode (no LLM)
python examples/03_reproduction.py code2logic/models.py --no-llm
```

## Duplicate Detection

```python
from code2logic import analyze_project

project = analyze_project("./my_project")

# Find duplicates by hash
from collections import defaultdict
import hashlib

duplicates = defaultdict(list)
for module in project.modules:
    for func in module.functions:
        sig = f"{func.name}({','.join(func.params)})"
        h = hashlib.md5(sig.encode()).hexdigest()[:8]
        duplicates[h].append(f"{module.path}::{func.name}")

# Report
for h, funcs in duplicates.items():
    if len(funcs) > 1:
        print(f"Duplicate group {h}:")
        for f in funcs:
            print(f"  - {f}")
```

## Local Quality / Duplicate Analysis

```bash
python examples/02_refactoring.py ./my_project
```

## LLM Refactoring Suggestions

```python
from code2logic import analyze_project
from code2logic.generators import CSVGenerator
import httpx

# Analyze
project = analyze_project("./my_project")
csv = CSVGenerator().generate(project, detail='standard')

# Get LLM suggestions
response = httpx.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5-coder:7b",
        "prompt": f"""Analyze this code and suggest refactoring:

{csv[:4000]}

List top 5 refactoring opportunities with effort estimates.""",
        "stream": False
    }
)
print(response.json()['response'])
```

## Token Efficiency Analysis

```python
from code2logic import analyze_project
from code2logic.generators import (
    MarkdownGenerator, CompactGenerator, JSONGenerator,
    YAMLGenerator, CSVGenerator
)
from code2logic.gherkin import GherkinGenerator

project = analyze_project("./my_project")

# Compare formats
formats = {
    'markdown': MarkdownGenerator().generate(project),
    'compact': CompactGenerator().generate(project),
    'json': JSONGenerator().generate(project),
    'yaml': YAMLGenerator().generate(project),
    'csv': CSVGenerator().generate(project),
    'gherkin': GherkinGenerator().generate(project),
}

for name, output in formats.items():
    tokens = len(output) // 4  # Approximate
    print(f"{name:12} {tokens:>6,} tokens")
```

## MCP Server Integration

Start the MCP server for Claude Desktop:

```bash
# Start server
python -m code2logic.mcp_server

# Or via make
make mcp-server
```

Configure Claude Desktop:

```json
{
  "mcpServers": {
    "code2logic": {
      "command": "python",
      "args": ["-m", "code2logic.mcp_server"]
    }
  }
}
```

# Quick start
python examples/01_quick_start.py

# Duplicate + quality analysis
python examples/02_refactoring.py

# Reproduce a file from a spec (LLM optional)
python examples/03_reproduction.py --show-spec
python examples/03_reproduction.py --no-llm

# Project reproduction (LLM optional)
python examples/04_project.py tests/samples/ --no-llm

# LLM integration demo (local analysis only)
python examples/05_llm_integration.py --no-llm

# Unified benchmarks (LLM optional)
python examples/15_unified_benchmark.py --type format --folder tests/samples/ --no-llm

# Terminal rendering demo
python examples/16_terminal_demo.py --folder tests/samples/
```

## See Also

- [CLI Reference](03-cli-reference.md) - Command-line options
- [Python API](04-python-api.md) - Programmatic interface
- [LLM Integration](08-llm-integration.md) - LLM provider setup

---

[← LLM Integration](08-llm-integration.md) | [Architecture →](13-architecture.md)
