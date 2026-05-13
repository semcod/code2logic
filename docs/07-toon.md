# TOON Format

> Token-Oriented Object Notation - Ultra-compact format for LLM consumption

[← README](../README.md) | [← Index](00-index.md) | [Format Specs →](06-format-specifications.md)

## Overview

TOON (Token-Oriented Object Notation) is a compact data format designed specifically for LLM input. It combines:
- **YAML-like** indentation for nesting
- **CSV-style** tabular arrays for uniform data
- **Minimal quoting** to reduce token usage

### Token Efficiency

| Format | Size | Tokens (~) | vs JSON |
|--------|------|------------|---------|
| **TOON** | 9,113 | ~2,278 | **17.0%** |
| Gherkin | 13,047 | ~3,261 | 24.4% |
| Markdown | 17,450 | ~4,362 | 32.6% |
| LogicML | 18,733 | ~4,683 | 35.0% |
| YAML | 23,537 | ~5,884 | 44.0% |
| JSON | 53,478 | ~13,369 | 100% |

**TOON is 6x smaller than JSON** - the most token-efficient format.

## Installation

TOON is included in Code2Logic by default:

```python
from code2logic import TOONGenerator, TOONParser, parse_toon
```

### Generate TOON

```python
from code2logic import analyze_project, TOONGenerator

project = analyze_project('/path/to/project')

# Standard TOON output
gen = TOONGenerator()
toon_output = gen.generate(project, detail='full')

# Ultra-compact TOON (71% smaller)
ultra_compact = gen.generate_ultra_compact(project)

# Generate JSON Schema
schema = gen.generate_schema('ultra_compact')  # or 'standard'

# With tabs (better for some LLMs)
gen_tabs = TOONGenerator(use_tabs=True)
toon_tabs = gen_tabs.generate(project)

print(f"Standard: {len(toon_output)} chars")
print(f"Ultra-compact: {len(ultra_compact)} chars")
```

### Ultra-Compact Format

New ultra-compact format with single-letter keys for maximum token efficiency:

```python
# Ultra-compact TOON
ultra = gen.generate_ultra_compact(project)
print(ultra)
```

**Sample Ultra-Compact Output:**
```
# Keys: M=modules, D=details, i=imports, c=classes, f=functions, m=methods
M[2]:
  utils.py,50
  main.py,100

D:
  utils.py:
    i: typing.{Dict,List},os.path
    c: Helper: get_version(0), validate_input(1)
    f: format_data()->str, load_config(path:str)->dict
  main.py:
    i: utils,click
    f: main()->None, cli()->None
```

**Schema Generation:**
```python
# Generate JSON Schema for validation
schema = gen.generate_schema('ultra_compact')
with open('toon-schema.json', 'w') as f:
    f.write(schema)
```

### Parse TOON

```python
from code2logic import parse_toon

toon_data = """
project: my_project
modules[2]{path,lang,lines}:
  utils.py,python,50
  main.py,python,100
"""

parsed = parse_toon(toon_data)
print(parsed['modules'])
# Generate TOON output
code2logic /path/to/project -f toon -o analysis.toon

# With full detail
code2logic /path/to/project -f toon -d full

# (when consecutive entries are in the same folder, emits ./file)
code2logic /path/to/project -f toon --no-repeat-module -o analysis.toon

# Generate function-logic as TOON + reduce repeats in function_details
code2logic /path/to/project -f toon --function-logic --name project -o ./ --no-repeat-details

# Output file: function.toon
code2logic /path/to/project -f toon --function-logic function.toon --name project -o ./

# - function-schema.json
code2logic /path/to/project -f toon --function-logic function.toon --with-schema --name project -o ./

# - function-schema.json
code2logic /path/to/project -f toon --compact --no-repeat-module --function-logic function.toon --with-schema --name project -o ./
```

### Reducing Path Repetition (Filesystem Tree Hint)

For large repositories, repeating directory prefixes in every `modules[...]` row or every `function_details` key can waste a lot of tokens.

Code2Logic supports a compact, LLM-friendly convention:

- The first entry in a directory is emitted as a full relative path, e.g. `scripts/build-docs.js`
- Subsequent consecutive entries in the same directory are emitted as `./<basename>`, e.g. `./seed_auth_users.py`

This signals "same directory as the previous entry" and is typically understood well by LLMs as a filesystem listing.

**Example (modules table):**

Without `--no-repeat-module`:

```toon
modules[4]{path,lang,lines,kb}:
  scripts/build-docs.js,js,9,1.2
  scripts/seed_auth_users.py,py,4,0.4
  scripts/stats-collector.py,py,14,0.8
  shared/dsl-runtime.ts,ts,13,1.1
```

With `--no-repeat-module`:

```toon
modules[4]{path,lang,lines,kb}:
  scripts/build-docs.js,js,9,1.2
  ./seed_auth_users.py,py,4,0.4
  ./stats-collector.py,py,14,0.8
  shared/dsl-runtime.ts,ts,13,1.1
```

**Example (function-logic TOON, function_details):**

```bash
code2logic /path/to/project -f toon --function-logic --with-schema --name project -o ./ --no-repeat-details
```

Output fragment:

```toon
# Convention: name with . = method, ~name = async, cc:N shown only when >1
project: myproject
generated: "2026-02-25T09:00:00"
modules[3]{path,lang,items}:
  firmware/main.py,py,4
  ./test_main.py,py,15
  db/config.py,py,5

function_details:
  firmware/main.py:
    functions[4]{line,name,sig}:
      77,~index_page cc:2,()
      85,~health_check,()
      90,~status,()
      96,"~websocket_endpoint cc:5","(websocket:WebSocket)"
  ./test_main.py:
    functions[15]{line,name,sig}:
      14,TestFirmwareSimulator.test_health_check,()
      20,TestFirmwareSimulator.test_scenarios_fetch,()
```

If you also want the intent/purpose column, add `--does`:

```bash
code2logic /path/to/project -f toon --function-logic --does --name project -o ./ --no-repeat-details
```

### Format Conventions (function-logic TOON)

| Convention | Meaning | Example |
|---|---|---|
| Name with `.` | Method | `Config.get_api_key` |
| Name without `.` | Top-level function | `main` |
| `~` prefix | Async | `~index_page` |
| `cc:N` suffix | Cyclomatic complexity > 1 | `~index_page cc:2` |
| `./file` | Same directory as previous entry | `./test_main.py` |

Only modules with at least one function/method are listed. Empty modules (`__init__.py`, `models.py` with 0 items) are omitted.

### The `--does` flag

By default, the `does` (intent/purpose) column is **omitted** from function-logic TOON to save tokens. Use `--does` to include it:

```bash
#     77,~index_page cc:2,(),Serve the firmware UI

code2logic /path/to/project -f toon --function-logic --does --name project -o ./
```

Use `--does` when you need the LLM to understand **what each function does**, not just its signature. Omit it when you only need structure/navigation.

### Schema Generation

When `--with-schema` is used with `--function-logic` and TOON format, a JSON schema is written alongside:

```bash
code2logic /path/to/project -f toon --function-logic function.toon --with-schema --name project -o ./
# Produces: function.toon + function-schema.json
```

If using `--stdout`, the function-logic schema is printed under the `=== FUNCTION_LOGIC_SCHEMA ===` section marker.

Notes:

- `--no-repeat-module` affects TOON `modules[...]` tables (main TOON output and function-logic TOON modules table).
- `--no-repeat-details` affects the module keys under `function_details` in function-logic TOON output.

### Language Codes

For lower token usage, TOON uses short language codes in `lang` columns and in `languages[...]` summary, e.g.:

- `py` = Python
- `js` = JavaScript
- `ts` = TypeScript

If a language is unknown or not mapped, the full language name is emitted.

### Basic Key-Value

```toon
project: my_project
version: 1.0.0
enabled: true
```

### Nested Objects

```toon
stats:
  files: 15
  lines: 1700
  languages:
    python: 10
    javascript: 5
```

### Tabular Arrays

Most powerful feature - CSV-style arrays with schema:

```toon
modules[3]{path,language,lines}:
  utils.py,python,50
  main.py,python,100
  helpers.js,javascript,30
```

Equivalent JSON:
```json
{
  "modules": [
    {"path": "utils.py", "language": "python", "lines": "50"},
    {"path": "main.py", "language": "python", "lines": "100"},
    {"path": "helpers.js", "language": "javascript", "lines": "30"}
  ]
}
```

### Primitive Arrays

Simple comma-separated values:

```toon
tags[3]: api,utils,core
imports[5]: typing,os,sys,json,pathlib
```

### Quoting Rules

Quote only when necessary:

```toon
# No quotes needed
name: simple_name
path: src/main.py

# Quotes required (special chars)
signature: "(self, data: str) -> bool"
description: "Process data, validate, and return"
```

## Complete Example

```toon
project: my_project
root: /home/user/project
stats:
  files: 2
  lines: 150
  languages[1]: python:2

modules[2]{path,lang,lines}:
  utils.py,python,50
  main.py,python,100

module_details:
  main.py:
    imports[3]: typing,dataclasses,pathlib
    classes[1]{name,bases,methods}:
      Application,BaseClass,5
    class_details:
      Application:
        doc: "Main application class"
        properties[2]: name:str,config:dict
        methods[3]{name,sig,async,lines}:
          __init__,"(self;name:str)",false,5
          run,(self)->int,false,10
          start,"(self;port:int)->None",true,8
    functions[1]{name,sig,intent}:
      main,()->None,"Entry point"
```

## Key Features

| Feature | Syntax | Description |
|---------|--------|-------------|
| **Tabular arrays** | `items[N]{f1,f2}:` | CSV-style for uniform data |
| **Primitive arrays** | `tags[N]: a,b,c` | Simple value lists |
| **Minimal quoting** | Only when needed | Reduces tokens |
| **Indentation** | 2 spaces | YAML-style nesting |
| **Explicit lengths** | `[N]` suffix | Helps LLM parsing |
| **Schema hints** | `{field1,field2}` | Clear structure |

### vs JSON
- **6x smaller** token usage
- Same data structure support
- Human readable

### vs YAML
- **2.5x smaller** for arrays
- Tabular syntax for uniform data
- Less verbose

### vs LogicML
- Similar compression
- Better for general data
- Simpler syntax

### TOONGenerator

```python
class TOONGenerator:
    def __init__(self, use_tabs: bool = False):
        """
        Args:
            use_tabs: Use tabs instead of spaces for indentation
        """
    
    def generate(self, project: ProjectInfo, detail: str = 'standard') -> str:
        """
        Generate TOON output.
        
        Args:
            project: Analyzed project info
            detail: 'minimal', 'standard', or 'full'
        
        Returns:
            TOON formatted string
        """
```

### TOONParser

```python
class TOONParser:
    def parse(self, content: str) -> dict:
        """
        Parse TOON content to dictionary.
        
        Args:
            content: TOON formatted string
        
        Returns:
            Parsed dictionary
        """
```

### Convenience Functions

```python
from code2logic import generate_toon, parse_toon

# Generate
toon_str = generate_toon(project)

# Parse
data = parse_toon(toon_str)
```

## Benchmarks

Run TOON benchmarks:

```bash
# Token benchmark with TOON
python examples/11_token_benchmark.py --formats json yaml toon

# Compare all formats
python examples/12_comprehensive_analysis.py
```

## See Also

- [Output Formats](05-output-formats.md) - All format comparison
- [Format Specifications](06-format-specifications.md) - Detailed specs
- [Benchmarking](10-benchmark.md) - Benchmark results
- [TOON GitHub](https://github.com/toon-format/toon) - Original spec

---

[← Format Specs](06-format-specifications.md) | [LLM Integration →](08-llm-integration.md)
