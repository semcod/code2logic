---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "getting-started",
  "kind": "information",
  "version": 1,
  "title": "Getting Started",
  "status": "proposed",
  "owner": "semcod/code2logic",
  "created": "2026-09-09",
  "updated": "2026-09-09",
  "review_after": "2026-10-09",
  "source_revision": "670066ca7c2383de95c85ab13740a3c34b1d9acb",
  "affected_repositories": [
    "semcod/code2logic"
  ],
  "evidence": [
    "https://github.com/semcod/code2logic/blob/670066ca7c2383de95c85ab13740a3c34b1d9acb/docs/01-getting-started.md"
  ]
}
---

# Getting Started

<!-- docs:section purpose -->
## Purpose

Preserve this reference while migrating links to the maintained canonical API documentation.

<!-- docs:section scope -->
## Scope

The original material below is retained from the source revision in metadata. This migration updates its placement and relative links; it is not a fresh validation of every historical example.

<!-- docs:section evidence -->
## Evidence

The immutable original document is linked in metadata. Current API corrections are documented in the project documentation index.

<!-- docs:section content -->
# Getting Started

> Quick installation and first steps with Code2Logic

[← README](../../README.md) | [← Index](index.md) | [Configuration →](configuration.md)

### From PyPI

```bash
pip install code2logic
```

### From Source

```bash
git clone https://github.com/wronai/code2logic.git
cd code2logic

# Recommended (Poetry)
poetry install -E full

# Alternatively (Makefile - prefers Poetry if available)
make install-full
```

# All optional dependencies (recommended)
pip install code2logic[full]

# Development setup (recommended)
poetry install --with dev -E full
```

# Basic analysis (Markdown output)
code2logic /path/to/project

# CSV format (best for data analysis)
code2logic /path/to/project -f csv -o analysis.csv

# Gherkin format (best for LLM, 95% accuracy)
code2logic /path/to/project -f gherkin -o analysis.feature

# Verbose mode with timing
code2logic /path/to/project -v
```

### Python Usage

```python
from code2logic import analyze_project

# Analyze a project
project = analyze_project("/path/to/project")

# Basic info
print(f"Files: {project.total_files}")
print(f"Lines: {project.total_lines}")
print(f"Languages: {list(project.languages.keys())}")

# Iterate modules
for module in project.modules:
    print(f"\n{module.path}:")
    for func in module.functions:
        print(f"  - {func.name}({', '.join(func.params)})")
```

## Output Formats

| Format | Command | Best For |
| ------ | ------- | -------- |
| Markdown | `-f markdown` | Documentation |
| CSV | `-f csv` | Data analysis |
| JSON | `-f json` | RAG/Embeddings |
| YAML | `-f yaml` | Human + LLM |
| Hybrid | `-f hybrid` | Code regeneration (best fidelity) |
| TOON | `-f toon` | Token-efficient specs |
| Gherkin | `-f gherkin` | LLM code gen (95%) |
| Compact | `-f compact` | Quick overview |

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen2.5-coder:7b

# Use with Code2Logic
code2logic ./my_project -f gherkin | ollama run qwen2.5-coder:7b "Review this"
```

# Set API key
export OPENROUTER_API_KEY="sk-or-v1-your-key"

# Run example
python examples/15_unified_benchmark.py --type file --file ./my_project/some_file.py
```

# Set in shell
export OPENROUTER_API_KEY="sk-or-v1-..."
export OLLAMA_HOST="http://localhost:11434"

# Or create .env file
cp .env.example .env
### Makefile Commands

```bash
make install       # Install (prefers Poetry if available)
make install-full  # Install with all features
make test          # Run tests
make lint          # Lint
make format        # Format
make typecheck     # Type checking
```

### Monorepo workflow (all packages)

If you work inside this repository (monorepo), you can manage all packages from the root folder:

```bash
make test-all
make build-subpackages
make publish-all
```

See: [Monorepo Workflow](../19-monorepo-workflow.md).

## Examples

Run the included examples:

```bash
# Quick start guide
python examples/01_quick_start.py

# BDD workflow
python examples/03_reproduction.py ./my_project/some_file.py --show-spec

# Token efficiency comparison
python examples/11_token_benchmark.py --folder ./my_project --no-llm

# Code review
python examples/02_refactoring.py ./my_project
```

## Next Steps

1. [Configure API keys](configuration.md) for LLM features
2. Learn [CLI commands](cli-reference.md)
3. Explore [Python API](python-api.md)
4. Try [Examples](examples.md)

---

[← Index](index.md) | [Configuration →](configuration.md)


<!-- docs:section limitations -->
## Limits

Unchanged historical examples remain subject to their original assumptions. Placement conformance does not establish semantic correctness or deployment.

<!-- docs:section next_actions -->
## Maintenance

Update this declared version when changing its substantive findings.
