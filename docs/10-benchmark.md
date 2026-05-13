# Code2Logic Benchmark Guide

[← README](../README.md) | [Docs Index](00-index.md)

## Overview

Benchmark results comparing specification formats for LLM code reproduction.
Test: 20 files from `tests/samples/`, model: `arcee-ai/trinity-large-preview`, date: 2026-02-25.

## Project Benchmark — Format Comparison

| Format | Score | Syntax OK | Runs OK | ~Tokens | Efficiency (p/kT) |
|--------|------:|----------:|--------:|--------:|---------:|
| **toon** | **63,8%** | 100% | 60% | 17 875 | **3,57** |
| json | 62,9% | 100% | 60% | 104 914 | 0,60 |
| markdown | 62,5% | 100% | 55% | 36 851 | 1,70 |
| yaml | 62,4% | 100% | 55% | 68 651 | 0,91 |
| logicml | 60,4% | 100% | 55% | ~30 000 | ~2,01 |
| csv | 53,0% | 100% | 40% | 80 779 | 0,66 |
| function.toon | 49,3% | 95% | 35% | 29 271 | 1,68 |
| gherkin | 38,6% | 95% | 30% | ~25 000 | ~1,54 |

**Behavioral benchmark:** 85,7% (6/7 functions passed).

### Key Metrics

- **Score** — overall reproduction quality (text + structural + semantic similarity), AST-based
- **Syntax OK** — % of generated code that compiles without errors
- **Runs OK** — % of generated code that executes successfully
- **Efficiency (p/kT)** — points per 1000 tokens (higher = better)

## Format Recommendations

| Use Case | Format | Reason |
|----------|--------|--------|
| **Best overall** | `toon` | Highest score at 5.9x fewer tokens than JSON |
| **Human-readable** | `yaml --compact` | Good balance of readability and size |
| **RAG / vector DB** | `json` | Easy to parse programmatically |
| **Function detail** | `function.toon --function-logic-context minimal` | With class context headers |
| **Hub-focused** | `toon --hybrid` | Project structure + function details for key modules |
| **Typed signatures** | `logicml` (level=typed) | Full type hints in compact format |

# Format benchmark only
python examples/15_unified_benchmark.py \
  --type format \
  --folder tests/samples/ \
  --formats yaml toon logicml json markdown csv gherkin function.toon \
  --limit 20 --verbose

# Project benchmark
python examples/15_unified_benchmark.py \
  --type project \
  --folder tests/samples/ \
  --formats yaml toon logicml json markdown csv gherkin function.toon \
  --limit 20 --verbose

# Function benchmark
python examples/15_unified_benchmark.py \
  --type function \
  --file tests/samples/sample_functions.py \
  --limit 10 --verbose

# Behavioral benchmark
python examples/behavioral_benchmark.py \
  --file tests/samples/sample_functions.py --verbose
```

# sample_class.py | Calculator | 74 lines

imports:
  stdlib: [typing.List, typing.Optional]

Calculator:
  doc: "Simple calculator with history."
  attrs:
    precision: int
    history: List[str]
  methods:
    add:
      sig: (a: float, b: float) -> float
      intent: "Add two numbers"
```

Generated Python:
```python
class Calculator:
    """Simple calculator with history."""
    
    def __init__(self, precision: int) -> None:
        self.precision = precision
        self.history: List[str] = []
    
    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        result = a + b
        self.history.append(f"add({a}, {b}) = {result}")
        return result
```

# sample_class.py | Calculator | 74 lines

imports:
  stdlib: [typing.List, typing.Optional]

Calculator:
  doc: "Simple calculator with history."
  attrs:
    precision: int
    history: List[str]
  methods:
    add:
      sig: (a: float, b: float) -> float
      does: "Add two numbers"
      side: "Modifies list"
    divide:
      sig: (a: float, b: float) -> Optional[float]
      does: "Divide a by b"
      edge: "b == 0 → return None"
```

### Gherkin Format (not recommended)
```gherkin
Feature: Calculator
  Simple calculator with history.

  Scenario: Add two numbers
    Given a calculator with precision 2
    When I add 2.5 and 3.5
    Then the result should be 6.0
    And the history should contain "add(2.5, 3.5) = 6.0"
```

**Problem**: Generates 2x more code with unnecessary error classes and over-engineering.

## Benchmark Scripts

| Script | Purpose |
|--------|---------|
| `11_token_benchmark.py` | Token-aware format comparison |
| `12_comprehensive_analysis.py` | Generated code quality analysis |
| `13_project_benchmark.py` | Entire project structure testing |
| `14_repeatability_test.py` | Code generation repeatability |

### Using LogicML (best compression)

```python
from code2logic import analyze_project, LogicMLGenerator

project = analyze_project('/path/to/project')
gen = LogicMLGenerator()
spec = gen.generate(project)

print(f"Tokens: ~{spec.token_estimate}")
print(spec.content)
```

### Using YAML (best quality)

```python
from code2logic import analyze_project
from code2logic.generators import YAMLGenerator

project = analyze_project('/path/to/project')
gen = YAMLGenerator()
spec = gen.generate(project, detail='full')

print(spec)
```

### Comparing Formats

```python
from code2logic import analyze_project
from code2logic.generators import YAMLGenerator
from code2logic.logicml import LogicMLGenerator
from code2logic.gherkin import GherkinGenerator

project = analyze_project('/path/to/project')

formats = {
    'yaml': YAMLGenerator().generate(project, detail='full'),
    'logicml': LogicMLGenerator().generate(project).content,
    'gherkin': GherkinGenerator().generate(project),
}

for name, spec in formats.items():
    tokens = len(spec) // 4
    print(f"{name}: {tokens} tokens, {len(spec)} chars")
```

### Key Findings

1. **TOON wins on efficiency** — best score (63,8%) at 5.9x fewer tokens than JSON
2. **Syntax OK = 100%** for all major formats — LLM always generates valid syntax
3. **Behavioral equivalence = 85,7%** — reproduced code actually works correctly
4. **function.toon paradox** — worse than project.toon (49,3% vs 63,8%) despite larger file, due to missing class/module context. Fixed with `--function-logic-context minimal`
5. **gherkin/csv** — poor fit for code description (38,6% / 53,0%)

### Improvements in v1.0.43

- AST-based structural scoring (replaces regex, ratio-based instead of binary)
- Reproduction prompts rewritten with format-specific parsing instructions
- function.toon now supports `--function-logic-context` for class/module headers
- LogicML default changed to `typed` level (10 params with full types)
- TOON-Hybrid format: project structure + function details for hub modules

## Environment Requirements

```bash
pip install python-dotenv httpx pyyaml
```

For LLM integration:
```bash
# OpenRouter (recommended)
export OPENROUTER_API_KEY=your_key

## Repeatability Analysis

Testing how consistent code generation is across multiple invocations.

# Test with 3 runs (default)
python examples/14_repeatability_test.py \
  --file tests/samples/sample_class.py

# Offline mode (template baseline)
python examples/14_repeatability_test.py \
  --file tests/samples/sample_class.py \
  --no-llm

# Test with 5 runs
python examples/14_repeatability_test.py \
  --file tests/samples/sample_class.py \
  --runs 5 \
  --formats yaml logicml gherkin
```

### Repeatability Results

| Format | Avg Similarity | Min Sim | Max Sim | Line Variance | Syntax OK |
|--------|---------------|---------|---------|---------------|-----------|
| **LogicML** | **56.9%** | 44.5% | **80.9%** | 94.9 | 100% |
| YAML | 41.0% | 29.3% | 61.8% | **8.7** | 100% |
| Gherkin | 14.1% | 2.0% | 24.9% | 374.9 | 100% |

### Key Findings

1. **LogicML is most consistent** - 56.9% average similarity between runs
2. **YAML has lowest variance** - 8.7 line variance (most stable output size)
3. **Gherkin is highly variable** - only 14.1% similarity, 375 line variance

### Code Differences Between Runs

| Format | Changed Lines | Stability |
|--------|--------------|-----------|
| YAML | 57 | Good |
| LogicML | 98 | Medium |
| Gherkin | 118 | Poor |

### Recommendations for Repeatability

1. **Use YAML for stable output** - lowest line variance
2. **Use LogicML for consistent logic** - highest similarity between runs
3. **Avoid Gherkin** - highly variable, unpredictable output

## Output Files

Benchmark results are saved to:
- `examples/output/token_benchmark.json`
- `examples/output/project_benchmark.json`
- `examples/output/comprehensive_analysis.json`
- `examples/output/repeatability_test.json`
- `examples/output/generated/{format}/` - Generated code files



