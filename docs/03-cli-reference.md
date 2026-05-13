# CLI Reference

> Command-line interface for Code2Logic

[← README](../README.md) | [← Configuration](02-configuration.md) | [Python API →](04-python-api.md)

## Basic Usage

```bash
code2logic /path/to/project [options]

# If the `code2logic` entrypoint is not available (e.g. running from source without install):
python -m code2logic /path/to/project [options]
```

## LLM Management

Code2Logic also provides LLM configuration and routing commands:

```bash
code2logic llm status
code2logic llm set-provider <provider>
code2logic llm set-model <provider> <model>
code2logic llm key set <provider> <api_key>
code2logic llm key unset <provider>
code2logic llm priority set-provider <provider> <priority>
code2logic llm priority set-model <model_name> <priority>
code2logic llm priority set-llm-model <model> <priority>
code2logic llm priority set-llm-family <prefix> <priority>
code2logic llm priority set-mode <provider-first|model-first|mixed>
code2logic llm config list
```

If `CODE2LOGIC_DEFAULT_PROVIDER=auto`, Code2Logic tries providers in priority order and picks the first one that is available.

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--format` | `-f` | Output format (markdown, compact, json, yaml, hybrid, csv, gherkin, toon, logicml) |
| `--output` | `-o` | Output file path |
| `--detail` | `-d` | Detail level (minimal, standard, full) |
| `--flat` | | Flat structure (for json/yaml formats) |
| `--compact` | | Use compact YAML format (14% smaller, meta.legend transparency) |
| `--hybrid` | | Use hybrid YAML output (or use `-f hybrid`) |
| `--ultra-compact` | | Use ultra-compact TOON format (71% smaller) |
| `--no-repeat-module` | | Reduce repeated directory prefixes in TOON `modules[...]` tables by using `./file` for consecutive entries in the same folder |
| `--no-repeat-details` | | Reduce repeated directory prefixes in function-logic TOON `function_details` section by using `./file` for consecutive entries in the same folder |
| `--does` | | Include the `does` (intent/purpose) column in function-logic TOON output. Omitted by default to save tokens |
| `--function-logic-context` | | Structural context in function-logic TOON: `none` (flat list), `minimal` (class headers with bases), `full` (classes + properties + imports). Default: `none` |
| `--hybrid` | | Use hybrid output. For TOON: combines project structure with function-logic details for hub modules. For YAML: use `-f hybrid` |
| `--with-schema` | | Generate JSON schema alongside output |
| `--verbose` | `-v` | Verbose output with timing |
| `--debug` | | Debug output (very verbose) |
| `--quiet` | `-q` | Suppress output except errors |
| `--no-install` | | Skip auto-installation of dependencies |
| `--no-treesitter` | | Disable Tree-sitter parser |
| `--status` | | Show library availability |
| `--version` | | Show version |

### Markdown (default)

```bash
code2logic /path/to/project -f markdown -o analysis.md
```

Human-readable documentation format with headers and code blocks.

### Gherkin (Best for LLM)

```bash
code2logic /path/to/project -f gherkin -o analysis.feature
```

BDD specification format. **Recommended for LLM code generation** (95% accuracy).

### CSV

```bash
code2logic /path/to/project -f csv -o analysis.csv
```

Tabular format, good for data analysis and spreadsheets.

# Nested JSON
code2logic /path/to/project -f json -o analysis.json

# Flat JSON (for RAG/embeddings)
code2logic /path/to/project -f json --flat -o analysis.json
```

# Standard YAML
code2logic /path/to/project -f yaml -o analysis.yaml

# Compact YAML (14% smaller, recommended for LLM)
code2logic /path/to/project -f yaml --compact -o analysis-compact.yaml

# Generate schema alongside output
code2logic /path/to/project -f yaml --compact --with-schema
```

Human-readable structured format with compact variant using short keys and `meta.legend` for LLM transparency.

# Hybrid YAML (recommended for code regeneration / best fidelity)
code2logic /path/to/project -f hybrid -o analysis.hybrid.yaml
```

# Standard TOON (token-efficient)
code2logic /path/to/project -f toon -o analysis.toon

# Function-logic TOON (outputs function.toon + optional schema)
code2logic /path/to/project -f toon --compact --function-logic function.toon --name project -o ./

# Same as above, but also compress repeated module paths and generate JSON Schema
code2logic /path/to/project -f toon --compact --no-repeat-module --function-logic function.toon --with-schema --name project -o ./

# Ultra-compact TOON (71% smaller, single-letter keys)
code2logic /path/to/project -f toon --ultra-compact -o analysis-ultra.toon

# Reduce repeated directory prefixes in modules[] (uses ./file when staying in the same folder)
code2logic /path/to/project -f toon --no-repeat-module -o analysis.toon

# Generate schema alongside output
code2logic /path/to/project -f toon --ultra-compact --with-schema

# Generate function-logic as TOON + compress function_details module keys
code2logic /path/to/project -f toon --function-logic --name project -o ./ --no-repeat-details

# Generate function-logic TOON with intent descriptions (does column)
code2logic /path/to/project -f toon --function-logic --does --name project -o ./

# Generate function-logic TOON with structural context (class headers before methods)
code2logic /path/to/project -f toon --function-logic function.toon \
  --function-logic-context minimal --name project -o ./

# Full structural context (classes + properties + imports)
code2logic /path/to/project -f toon --function-logic function.toon \
  --function-logic-context full --name project -o ./

# TOON-Hybrid (project structure + function details for top hub modules)
code2logic /path/to/project -f toon --hybrid --no-repeat-module --name project -o ./

# Generate function-logic TOON + schema (function.toon + function-schema.json)
code2logic /path/to/project -f toon --function-logic function.toon --with-schema --name project -o ./
```

Token-oriented object notation - most efficient format for LLM consumption (5.9x smaller than JSON).

## Benchmarks (Makefile)

This repository includes reproducibility benchmarks that compare formats by how well they can be used to regenerate runnable code (heuristic scoring).

```bash
make benchmark
```

Generated artifacts (written to `examples/output/`):

- `BENCHMARK_REPORT.md`
  - Links all artifacts and summarizes the run
- `BENCHMARK_COMMANDS.sh`
  - Exact commands used to generate each artifact
- `benchmark_format.json`, `benchmark_project.json`, `benchmark_token.json`, `benchmark_function.json`
  - Raw benchmark results
- `project.toon`, `function.toon` (+ `*-schema.json`)
  - Self-analysis outputs used for size/token comparisons

Run all example scripts step-by-step:

```bash
make examples
```

## Detail Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| `minimal` | Basic structure only | Quick overview, low tokens |
| `standard` | Structure + metadata | General analysis |
| `full` | Everything including docstrings | Detailed analysis |

```bash
# Minimal detail (smallest output)
code2logic /path/to/project -f csv -d minimal

# Standard detail (default)
code2logic /path/to/project -f csv -d standard

# Full detail (most comprehensive)
code2logic /path/to/project -f csv -d full
```

# Analyze specific project
code2logic /path/to/myproject
```

# Save as Gherkin
code2logic /path/to/project -f gherkin -o tests.feature

# Save as JSON
code2logic /path/to/project -f json -o analysis.json
```

# Show progress and statistics
code2logic /path/to/project -v

# Pipe to jq for JSON processing
code2logic /path/to/project -f json | jq '.modules[0]'

# Pipe to grep
code2logic /path/to/project -f csv | grep "function"

# Count functions
code2logic /path/to/project -f csv -d minimal | wc -l
```

# Generate context for LLM prompt
code2logic /path/to/project -f gherkin -d minimal > context.feature

# Use with Ollama
cat context.feature | ollama run qwen2.5-coder:7b "Generate tests for this"
```

# Skip dependency installation
CODE2LOGIC_NO_INSTALL=1 code2logic /path/to/project

# Same, when running from source without install
CODE2LOGIC_NO_INSTALL=1 python -m code2logic /path/to/project

# Enable verbose mode
CODE2LOGIC_VERBOSE=true code2logic /path/to/project
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (invalid path, parse error, etc.) |

## See Also

- [Output Formats](05-output-formats.md) - Detailed format comparison
- [Python API](04-python-api.md) - Programmatic usage
- [Examples](12-examples.md) - More usage examples
- [LLM Integration](08-llm-integration.md) - Provider setup and LLM workflows

---

[← Configuration](02-configuration.md) | [Python API →](04-python-api.md)
