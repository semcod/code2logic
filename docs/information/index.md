---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "index",
  "kind": "information",
  "version": 1,
  "title": "Code2Logic Documentation",
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
    "https://github.com/semcod/code2logic/blob/670066ca7c2383de95c85ab13740a3c34b1d9acb/docs/00-index.md"
  ]
}
---

# Code2Logic Documentation

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
# Code2Logic Documentation

Convert source code to logical representation for LLM analysis

[← README](../../README.md)

## Quick Navigation

| # | Document | Description |
| --- | -------- | ----------- |
| 01 | [Getting Started](getting-started.md) | Installation and first steps |
| 02 | [Configuration](configuration.md) | API keys, environment setup |
| 03 | [CLI Reference](cli-reference.md) | Command-line usage |
| 04 | [Python API](python-api.md) | Programmatic usage |
| 05 | [Output Formats](output-formats.md) | Format comparison and usage |
| 06 | [Format Specifications](../06-format-specifications.md) | Detailed format specs |
| 07 | [TOON Format](toon.md) | Token-Oriented Object Notation |
| 08 | [LLM Integration](llm-integration.md) | OpenRouter, Ollama, LiteLLM |
| 09 | [LLM Comparison](../09-llm-comparison-report.md) | Provider/model comparison |
| 10 | [Benchmarking](benchmark.md) | Benchmark methodology |
| 11 | [Repeatability](repeatability.md) | Repeatability testing |
| 12 | [Examples](examples.md) | Usage examples and workflows |
| 13 | [Architecture](architecture.md) | System design and components |
| 14 | [Format Analysis](../14-format-analysis.md) | Deeper format evaluation |
| 15 | [Logic2Test](../15-logic2test.md) | Test generation from logic files |
| 16 | [Logic2Code](../16-logic2code.md) | Code generation from logic files |
| 17 | [LOLM](../17-lolm.md) | LLM provider management |
| 18 | [Reproduction Testing](../18-reproduction-testing.md) | Format validation and code regeneration |
| 19 | [Monorepo Workflow](../19-monorepo-workflow.md) | Managing all packages from repo root |
| 20 | [LLM Benchmarks + Claude](llm-benchmarks-claude.md) | Run benchmarks with LLM enabled and force Claude (Anthropic) |

## Repository Links

- [README](../../README.md)
- [Changelog](../../CHANGELOG.md)
- [Refactoring Plan](../../TODO.md)

## Overview

Code2Logic analyzes codebases and generates structured representations optimized for LLM consumption. It supports multiple output formats, each designed for specific use cases.

### Key Features

| Feature | Description |
| ------- | ----------- |
| Multi-format output | Markdown, JSON, YAML, TOON, LogicML, Gherkin, CSV |
| LLM-optimized | Token-efficient formats (TOON is 5.9x smaller than JSON) |
| TOON-Hybrid | Project structure + selective function details for hub modules |
| AST-based scoring | Accurate structural comparison using Python AST |
| Duplicate Detection | Find similar/duplicate functions |
| Dependency Analysis | PageRank, hub detection, clustering |
| Multiple Languages | Python, JavaScript, TypeScript, Go, Rust, Java |

### Format Comparison (Feb 2026, 20 files)

| Format | Score | ~Tokens | Efficiency (p/kT) | Best For |
| ------ | -----:| -------:| ---------:| -------- |
| **toon** | **63,8%** | 17 875 | **3,57** | Token efficiency (smallest) |
| json | 62,9% | 104 914 | 0,60 | RAG/embeddings |
| markdown | 62,5% | 36 851 | 1,70 | Documentation |
| yaml | 62,4% | 68 651 | 0,91 | Human + LLM |
| logicml | 60,4% | ~30 000 | ~2,01 | Compression + typed sigs |
| csv | 53,0% | 80 779 | 0,66 | Data analysis |
| function.toon | 49,3% | 29 271 | 1,68 | Function-level detail |
| gherkin | 38,6% | ~25 000 | ~1,54 | BDD scenarios |

# Install
pip install code2logic

# Analyze project
code2logic /path/to/project -f gherkin -o analysis.feature

# With Python
from code2logic import analyze_project
project = analyze_project("/path/to/project")
print(f"Files: {project.total_files}")
```

# Set API keys for LLM features
export OPENROUTER_API_KEY="sk-or-v1-..."
export OLLAMA_HOST="http://localhost:11434"

# Or use .env file
cp .env.example .env
# Edit .env with your keys
```

See [Configuration Guide](configuration.md) for details.

## Links

- [GitHub Repository](https://github.com/wronai/code2logic)
- [PyPI Package](https://pypi.org/project/code2logic)
- [Issue Tracker](https://github.com/wronai/code2logic/issues)

Generated by Code2Logic


<!-- docs:section limitations -->
## Limits

Unchanged historical examples remain subject to their original assumptions. Placement conformance does not establish semantic correctness or deployment.

<!-- docs:section next_actions -->
## Maintenance

Update this declared version when changing its substantive findings.
