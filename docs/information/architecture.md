---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "architecture",
  "kind": "information",
  "version": 1,
  "title": "Architecture and extension contracts",
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
    "https://github.com/semcod/code2logic/blob/670066ca7c2383de95c85ab13740a3c34b1d9acb/code2logic/llm/__init__.py",
    "https://github.com/semcod/code2logic/blob/670066ca7c2383de95c85ab13740a3c34b1d9acb/code2logic/base.py",
    "https://github.com/semcod/code2logic/blob/670066ca7c2383de95c85ab13740a3c34b1d9acb/docs/13-architecture.md"
  ]
}
---

# Architecture and extension contracts

<!-- docs:section purpose -->
## Purpose

Describe the current Python API and extension points.

<!-- docs:section scope -->
## Scope

This reference describes the repository revision above. Optional LLM clients require their configured provider dependencies.

<!-- docs:section evidence -->
## Evidence

The exported client is `OllamaLocalClient`; the base classes are owned by `code2logic.base`. The previous reference remains auditable at the immutable source URL in metadata. The May formatting commit touched code and docs together; it does not establish semantic recency. A later August documentation edit changed unrelated MCP guidance, leaving the old client import unchanged.

<!-- docs:section content -->
# Architecture

> System design and component overview

[← README](../../README.md) | [← Examples](examples.md) | [Index →](index.md)

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       Code2Logic                             │
├─────────────────────────────────────────────────────────────┤
│  CLI (cli.py)          │  Python API (__init__.py)          │
├─────────────────────────────────────────────────────────────┤
│                    ProjectAnalyzer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ TreeSitter   │  │ Universal    │  │ Dependency   │       │
│  │ Parser       │  │ Parser       │  │ Analyzer     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                      Generators                              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Markdown│ │ JSON   │ │ YAML   │ │ CSV    │ │Gherkin │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    LLM Integration                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Ollama       │  │ OpenRouter   │  │ LiteLLM      │       │
│  │ Client       │  │ Client       │  │ Client       │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Component Diagram

```
                    ┌─────────────┐
                    │   User      │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
        ┌─────▼─────┐            ┌──────▼──────┐
        │    CLI    │            │  Python API │
        │  cli.py   │            │ __init__.py │
        └─────┬─────┘            └──────┬──────┘
              │                         │
              └────────────┬────────────┘
                           │
                    ┌──────▼──────┐
                    │  Analyzer   │
                    │ analyzer.py │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   ┌─────▼─────┐    ┌──────▼──────┐   ┌─────▼─────┐
   │TreeSitter │    │  Universal  │   │Dependency │
   │  Parser   │    │   Parser    │   │ Analyzer  │
   └─────┬─────┘    └──────┬──────┘   └─────┬─────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Models    │
                    │ ProjectInfo │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   ┌─────▼─────┐    ┌──────▼──────┐   ┌─────▼─────┐
   │ Markdown  │    │    JSON     │   │  Gherkin  │
   │ Generator │    │  Generator  │   │ Generator │
   └───────────┘    └─────────────┘   └───────────┘
```

### ProjectAnalyzer (`analyzer.py`)

Main orchestrator that coordinates parsing and analysis.

```python
class ProjectAnalyzer:
    def __init__(self, root_path, use_treesitter=True, verbose=False):
        self.root_path = root_path
        self.parser = TreeSitterParser() if use_treesitter else UniversalParser()
    
    def analyze(self) -> ProjectInfo:
        files = self._scan_files()
        modules = [self.parser.parse_file(f) for f in files]
        return ProjectInfo(modules=modules, ...)
```

### Parsers (`parsers.py`)

**TreeSitterParser** - AST-based parsing using Tree-sitter.
- Accurate function/class detection
- Supports Python, JavaScript, TypeScript, Go, Rust

**UniversalParser** - Regex-based fallback.
- Works without Tree-sitter
- Less accurate but universal

### Generators (`generators.py`)

Convert `ProjectInfo` to various output formats:

| Generator | Output | Method |
|-----------|--------|--------|
| `MarkdownGenerator` | `.md` | `generate(project, detail)` |
| `JSONGenerator` | `.json` | `generate(project, flat, detail)` |
| `YAMLGenerator` | `.yaml` | `generate(project, flat, detail)` |
| `CSVGenerator` | `.csv` | `generate(project, detail)` |
| `CompactGenerator` | `.txt` | `generate(project)` |

### Gherkin (`gherkin.py`)

BDD specification generation:

- `GherkinGenerator` - Feature files
- `StepDefinitionGenerator` - pytest-bdd steps
- `CucumberYAMLGenerator` - Cucumber format

### LLM Clients (`llm.py`)

```python
class OllamaClient:
    def generate(self, prompt, system=None) -> str
    def chat(self, messages) -> str
    def is_available(self) -> bool

class LiteLLMClient:
    # Same interface, uses LiteLLM library
```

### Configuration (`config.py`)

Environment and API key management:

```python
class Config:
    def get_api_key(self, provider) -> str
    def get_model(self, provider) -> str
    def list_configured_providers() -> Dict[str, bool]
```

## Data Models (`models.py`)

```python
@dataclass
class ProjectInfo:
    name: str
    modules: List[ModuleInfo]
    total_files: int
    total_lines: int

@dataclass
class ModuleInfo:
    path: str
    functions: List[FunctionInfo]
    classes: List[ClassInfo]

@dataclass
class FunctionInfo:
    name: str
    params: List[str]
    return_type: str
    intent: str

@dataclass
class ClassInfo:
    name: str
    bases: List[str]
    methods: List[FunctionInfo]
```

## Data Flow

```
1. Input: Project path
   │
2. Scan: Find source files
   │
3. Parse: Extract AST/structure
   │
4. Analyze: Build ProjectInfo
   │
5. Generate: Convert to output format
   │
6. Output: File or stdout
```

## File Structure

```
code2logic/
├── __init__.py       # Public API exports
├── __main__.py       # Module entry point
├── analyzer.py       # ProjectAnalyzer
├── cli.py            # Command-line interface
├── config.py         # Configuration management
├── dependency.py     # Dependency analysis
├── generators.py     # Output generators
├── gherkin.py        # BDD/Gherkin generation
├── intent.py         # Intent inference
├── llm.py            # LLM clients
├── mcp_server.py     # MCP protocol server
├── models.py         # Data models
├── parsers.py        # Code parsers
└── similarity.py     # Duplicate detection
```

### Adding New Generator

```python
from code2logic.base import BaseGenerator

class CustomGenerator(BaseGenerator):
    def generate(self, project: ProjectInfo, **kwargs) -> str:
        # Your implementation
        return output_string
```

### Adding New Parser

```python
from code2logic.base import BaseParser

class CustomParser(BaseParser):
    def parse_file(self, path: str) -> ModuleInfo:
        # Your implementation
        return ModuleInfo(...)
```

### Adding New LLM Client

```python
from code2logic.llm import BaseLLMClient

class CustomClient(BaseLLMClient):
    def generate(self, prompt: str, system: str = None) -> str:
        # Your implementation
        return response
```

## Performance Considerations

- **Tree-sitter** is faster for large codebases
- **Fallback parser** uses more memory for complex files
- **Generators** are streaming-capable for large outputs
- **LLM calls** are the main bottleneck

## See Also

- [Python API](python-api.md) - Detailed API reference
- [Configuration](configuration.md) - Setup guide
- [TODO.md](../../TODO.md) - Refactoring roadmap

---

[← Examples](examples.md) | [Index →](index.md)


<!-- docs:section limitations -->
## Validation limits

The corrected imports were checked against source definitions and exports. Provider requests and tutorial workloads were not executed; their credentials and external services remain explicit prerequisites.

<!-- docs:section next_actions -->
## Maintenance

Update this reference and its declared version when the public API changes.
