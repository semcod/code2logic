# Output Formats

> Comparison and usage guide for all output formats

[← README](../README.md) | [← Python API](04-python-api.md) | [LLM Integration →](08-llm-integration.md)

## Format Overview

| Format | Tokens | Accuracy | Best For |
|--------|--------|----------|----------|
| **TOON** | ~2K | 70% | Token efficiency (6x smaller than JSON) |
| **Gherkin** | ~3K | 95% | LLM code generation |
| **Hybrid YAML** | ~6K | 90% | Code regeneration (best fidelity) |
| **YAML** | ~6K | 90% | Human + LLM |
| **LogicML** | ~5K | 65% | Compression + async code |
| **Compact** | ~200 | 50% | Quick overview |
| **CSV** | ~4K | 70% | Data analysis |
| **Markdown** | ~4K | 60% | Documentation |
| **JSON** | ~12K | 75% | RAG/Embeddings |

## Gherkin (Recommended for LLM)

BDD specification format with highest LLM accuracy.

```bash
code2logic /path/to/project -f gherkin -o analysis.feature
```

**Sample output:**
```gherkin
@core @large
Feature: Core Functionality
  BDD tests for core module

  @lifecycle
  Scenario Outline: Lifecycle operations
    Given the system is initialized
    When user calls <function>
    Then the operation completes

    Examples:
      | function | params | returns |
      | __init__ | self,config | void |
      | analyze | self,path | ProjectInfo |
```

**Best for:**
- LLM code generation (95% accuracy)
- BDD test generation
- Behavior documentation

## YAML

Human-readable structured format with compact and full variants.

```bash
# Standard YAML
code2logic /path/to/project -f yaml -o analysis.yaml

# Compact YAML (recommended for LLM)
code2logic /path/to/project -f yaml --compact -o analysis-compact.yaml

# Generate schema alongside output
code2logic /path/to/project -f yaml --compact --with-schema
```

**Compact YAML Sample:**
```yaml
meta:
  legend:
    p: path
    l: lines
    i: imports
    e: exports
    c: classes
    f: functions
    n: name
    d: docstring
    b: bases
    m: methods
    sig: signature (without self)
    ret: return_type
    async: is_async
defaults:
  lang: python
modules:
- p: src/analyzer.py
  l: 221
  i:
  - typing.{Dict,List,Optional}
  - dataclasses.dataclass
  c:
  - n: ProjectAnalyzer
    d: Analyzes project structure and dependencies
    m:
    - n: analyze
      sig: (path:str)->ProjectInfo
      ret: ProjectInfo
```

**Full YAML Sample:**
```yaml
project: myproject
statistics:
  files: 30
  lines: 10835
  languages:
    python: 30

modules:
  - path: src/analyzer.py
    language: python
    lines: 221
    imports:
      - typing.Dict
      - typing.List
      - dataclasses
    functions:
      - name: analyze
        signature: (self, path) -> ProjectInfo
        intent: Analyzes project structure
```

**Best for:**
- **Compact**: LLM processing (14% smaller, meta.legend transparency)
- **Full**: Human review + detailed analysis
- Configuration files
- API documentation

**Schema Generation:**
YAML formats support JSON Schema generation for validation and LLM guidance:
```python
from code2logic.generators import YAMLGenerator

gen = YAMLGenerator()
schema = gen.generate_schema('compact')  # or 'full'
```

## Hybrid YAML

Hybrid YAML is optimized for code regeneration workflows (best balance of fidelity and size).

```bash
code2logic /path/to/project -f hybrid -o analysis.hybrid.yaml
```

## Compact

Ultra-minimal format (~200 tokens).

```bash
code2logic /path/to/project -f compact -o analysis.txt
```

**Sample output:**
```
# myproject | 30f 10835L | python:30

ENTRY: cli.py analyzer.py

  analyzer.py (221L) C:ProjectAnalyzer | F:analyze,scan
  cli.py (298L) C:Colors,Logger | F:main
  models.py (154L) -
```

**Best for:**
- Quick overview
- Low token budgets
- File structure summary

## CSV

Tabular format for data analysis.

```bash
code2logic /path/to/project -f csv -o analysis.csv
```

**Sample output:**
```csv
path,type,name,signature,language,intent,category
analyzer.py,class,ProjectAnalyzer,(),python,,other
analyzer.py,method,analyze,(self,path)->ProjectInfo,python,Analyzes project,transform
cli.py,function,main,(),python,Entry point,lifecycle
```

**Best for:**
- Data analysis
- Spreadsheet import
- Filtering/sorting

## Markdown

Human-readable documentation.

```bash
code2logic /path/to/project -f markdown -o analysis.md
```

**Sample output:**
```markdown
# myproject

**Files:** 30 | **Lines:** 10,835

#### ProjectAnalyzer

**Methods:**
- `analyze(path) -> ProjectInfo` - Analyzes project structure
- `scan_files() -> List[str]` - Scans for source files

### Functions

- `get_statistics()` - Returns analysis statistics
```

**Best for:**
- Documentation
- Human reading
- GitHub/GitLab display

## JSON

Structured data format.

```bash
# Nested JSON
code2logic /path/to/project -f json -o analysis.json

# Flat JSON (for RAG)
code2logic /path/to/project -f json --flat -o analysis.json
```

**Nested sample:**
```json
{
  "project": {
    "name": "myproject",
    "total_files": 30
  },
  "modules": [
    {
      "path": "analyzer.py",
      "functions": [
        {"name": "analyze", "params": ["self", "path"]}
      ]
    }
  ]
}
```

**Flat sample (for RAG):**
```json
[
  {"path": "analyzer.py", "type": "function", "name": "analyze"},
  {"path": "analyzer.py", "type": "class", "name": "ProjectAnalyzer"}
]
```

**Best for:**
- RAG/Embeddings (flat)
- API responses
- Programmatic processing

## Detail Levels

All formats (except Compact) support three detail levels:

| Level | Description | Tokens |
|-------|-------------|--------|
| `minimal` | Structure only | ~1x |
| `standard` | + metadata | ~1.5x |
| `full` | + docstrings, code | ~2x |

```bash
code2logic /path/to/project -f csv -d minimal
code2logic /path/to/project -f csv -d standard
code2logic /path/to/project -f csv -d full
```

## Token Comparison

Based on analysis of `code2logic/` (13 files, 5,618 lines):

| Format | Minimal | Standard | Full |
|--------|---------|----------|------|
| Compact | 223 | - | - |
| Gherkin | 2,903 | 6,176 | 7,570 |
| CSV | 7,958 | 12,957 | 15,343 |
| Markdown | - | 8,616 | - |
| YAML | - | 11,102 | - |
| JSON | - | 21,799 | 31,926 |

## Cost Comparison (GPT-4)

| Format | Cost/Call | Monthly (10/day) |
|--------|-----------|------------------|
| Compact | $0.007 | $2 |
| Gherkin | $0.087 | $26 |
| CSV | $0.113 | $34 |
| Markdown | $0.130 | $39 |
| YAML | $0.177 | $53 |
| JSON | $0.357 | $107 |

## Choosing a Format

```
Need best token efficiency?   → TOON (6x smaller than JSON)
Need LLM code generation?     → Gherkin or YAML
Need human + LLM readability? → YAML
Need minimal tokens?          → Compact
Need data analysis?           → CSV
Need documentation?           → Markdown
Need RAG/embeddings?          → JSON flat
Need async code handling?     → LogicML
```

## See Also

- [TOON Format](07-toon.md) - Token-Oriented Object Notation
- [Format Specifications](06-format-specifications.md) - Detailed format specs
- [CLI Reference](03-cli-reference.md) - Command-line options
- [LLM Integration](08-llm-integration.md) - Using with LLMs
- [examples/11_token_benchmark.py](../examples/11_token_benchmark.py) - Token-aware benchmark

---

[← Python API](04-python-api.md) | [LLM Integration →](08-llm-integration.md)
