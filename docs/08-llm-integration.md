# LLM Integration Guide

> Using Code2Logic with Large Language Models

[← README](../README.md) | [← Output Formats](05-output-formats.md) | [Examples →](12-examples.md)

## Overview

Code2Logic generates LLM-optimized representations of codebases. This guide covers integration with various LLM providers.

In addition to exporting LLM-friendly formats, Code2Logic provides a CLI for managing LLM configuration:

```bash
code2logic llm status
code2logic llm set-provider auto
code2logic llm key set openrouter <OPENROUTER_API_KEY>
code2logic llm set-model openrouter nvidia/nemotron-3-nano-30b-a3b:free
```

## Supported Providers

| Provider | Type | Setup |
|----------|------|-------|
| [OpenRouter](#openrouter) | Cloud | API key |
| [Ollama](#ollama) | Local | Install |
| [OpenAI](#openai) | Cloud | API key |
| [Anthropic](#anthropic) | Cloud | API key |
| [LiteLLM](#litellm) | Universal | pip install |

## OpenRouter

Best for accessing multiple models through one API.

# Get API key from https://openrouter.ai/keys
export OPENROUTER_API_KEY="sk-or-v1-your-key"
export OPENROUTER_MODEL="qwen/qwen-2.5-coder-32b-instruct"

# Or configure via CLI (.env)
code2logic llm key set openrouter <OPENROUTER_API_KEY>
code2logic llm set-model openrouter qwen/qwen-2.5-coder-32b-instruct
```

### Recommended Models

| Model | Best For | Cost |
|-------|----------|------|
| `qwen/qwen-2.5-coder-32b-instruct` | Code generation | $$ |
| `deepseek/deepseek-coder-33b-instruct` | Code analysis | $$ |
| `anthropic/claude-3-haiku` | Fast responses | $ |
| `meta-llama/llama-3.1-70b-instruct` | General | $$ |

### Example

```python
from code2logic import analyze_project
from code2logic.gherkin import GherkinGenerator
import httpx

# Analyze code
project = analyze_project("./my_project")
gherkin = GherkinGenerator().generate(project, detail='standard')

# Send to OpenRouter
response = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json"
    },
    json={
        "model": "qwen/qwen-2.5-coder-32b-instruct",
        "messages": [
            {"role": "system", "content": "You are a code expert."},
            {"role": "user", "content": f"Analyze this code:\n{gherkin}"}
        ]
    }
)
print(response.json()['choices'][0]['message']['content'])
```

## Ollama

Best for local, private, and free LLM usage.

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull code-optimized model
ollama pull qwen2.5-coder:14b

### Configuration

```bash
export OLLAMA_HOST="http://localhost:11434"
export OLLAMA_MODEL="qwen2.5-coder:14b"

# Or configure via CLI (.env)
code2logic llm set-model ollama qwen2.5-coder:14b
```

### Default provider

```bash
code2logic llm set-provider ollama
code2logic llm set-provider openrouter
```

### Automatic fallback (recommended)

```bash
code2logic llm set-provider auto
```

When `CODE2LOGIC_DEFAULT_PROVIDER=auto`, Code2Logic tries providers in priority order and picks the first one that is available.

### Setting provider priority

Provider priorities can be set even if there are no matching entries in `litellm_config.yaml`:

```bash
code2logic llm priority set-provider openrouter 10
code2logic llm priority set-provider ollama 20
```

Provider priority overrides and model rules are stored in:

- `~/.code2logic/llm_config.json`

### Model priority (independent of provider)

You can prioritize specific models or model families (prefix):

```bash
code2logic llm priority set-llm-model nvidia/nemotron-3-nano-30b-a3b:free 5
code2logic llm priority set-llm-family nvidia/ 5
```

### Priority modes

Choose how priorities are resolved:

```bash
code2logic llm priority set-mode provider-first
code2logic llm priority set-mode model-first
code2logic llm priority set-mode mixed
```

- `provider-first`: provider priority controls ordering
- `model-first`: model rules control ordering (fallback to provider priority)
- `mixed`: best (lowest) priority wins

### Example

```python
from code2logic import analyze_project
from code2logic.llm import OllamaClient

# Analyze code
project = analyze_project("./my_project")

# Use Ollama
client = OllamaClient(model="qwen2.5-coder:14b")
response = client.generate(
    prompt=f"Analyze this project:\n{project.total_files} files",
    system="You are a code reviewer."
)
print(response)
```

# Generate analysis and pipe to Ollama
code2logic ./my_project -f gherkin -d minimal | \
  ollama run qwen2.5-coder:7b "Generate unit tests for this code"
```

### Setup

```bash
export OPENAI_API_KEY="sk-your-key"
export OPENAI_MODEL="gpt-4-turbo"
```

### Example

```python
from openai import OpenAI
from code2logic import analyze_project
from code2logic.generators import CSVGenerator

client = OpenAI()
project = analyze_project("./my_project")
csv_output = CSVGenerator().generate(project, detail='standard')

response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[
        {"role": "system", "content": "You are a code analyst."},
        {"role": "user", "content": f"Review this code:\n{csv_output}"}
    ]
)
print(response.choices[0].message.content)
```

### Setup

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key"
export ANTHROPIC_MODEL="claude-3-sonnet-20240229"
```

### Example

```python
from anthropic import Anthropic
from code2logic import analyze_project
from code2logic.gherkin import GherkinGenerator

client = Anthropic()
project = analyze_project("./my_project")
gherkin = GherkinGenerator().generate(project)

response = client.messages.create(
    model="claude-3-sonnet-20240229",
    max_tokens=4000,
    messages=[
        {"role": "user", "content": f"Analyze this code:\n{gherkin}"}
    ]
)
print(response.content[0].text)
```

## LiteLLM

Universal interface for all LLM providers.

### Setup

```bash
pip install litellm
```

### Example

```python
import litellm
from code2logic import analyze_project
from code2logic.gherkin import GherkinGenerator

project = analyze_project("./my_project")
gherkin = GherkinGenerator().generate(project, detail='minimal')

# Works with any provider
response = litellm.completion(
    model="ollama/qwen2.5-coder:7b",  # or "gpt-4", "claude-3-sonnet", etc.
    messages=[
        {"role": "system", "content": "You are a code expert."},
        {"role": "user", "content": f"Review:\n{gherkin}"}
    ]
)
print(response.choices[0].message.content)
```

## Code Reproduction Workflow

Complete workflow: Code → Gherkin → LLM → Code

```bash
# Run a benchmark example (uses CODE2LOGIC_DEFAULT_PROVIDER + provider env vars)
CODE2LOGIC_DEFAULT_PROVIDER=openrouter python examples/15_unified_benchmark.py --type file --file code2logic/models.py

# Or local/offline mode
python examples/15_unified_benchmark.py --type file --file code2logic/models.py --no-llm
```

### Workflow Steps

1. **Analyze** - Convert code to Gherkin specification
2. **Generate** - LLM generates code from Gherkin
3. **Compare** - Measure reproduction quality

```python
# Step 1: Analyze
from code2logic import analyze_project
from code2logic.gherkin import GherkinGenerator

project = analyze_project("./my_project")
gherkin = GherkinGenerator().generate(project, detail='full')

# Step 2: Generate with LLM
prompt = f"""Generate Python code for this specification:

{gherkin}

Output complete, working code."""

response = llm_client.generate(prompt)

### Token Efficiency

| Format | Tokens | Accuracy | When to Use |
|--------|--------|----------|-------------|
| Gherkin minimal | ~3K | 95% | Code generation |
| CSV minimal | ~8K | 70% | Analysis |
| Compact | ~200 | 50% | Quick overview |

# Good: Specific task with context
prompt = f"""Given this code structure:
{gherkin}

Task: Generate unit tests for the UserService class.
Requirements:
- Use pytest
- Mock external dependencies
- Cover edge cases"""

# Bad: Vague request
prompt = f"Write tests for {gherkin}"
```

### Cost Optimization

1. Use **Gherkin minimal** for code generation
2. Use **Compact** for quick queries
3. Use **local Ollama** for development
4. Use **cloud LLMs** for production

## MCP Server Integration

For Claude Desktop / Windsurf:

```json
// ~/.config/claude/claude_desktop_config.json
{
  "mcpServers": {
    "code2logic": {
      "command": "python",
      "args": ["-m", "code2logic.mcp_server"]
    }
  }
}
```

See [Examples](12-examples.md) for more integration patterns.

---

[← Output Formats](05-output-formats.md) | [Examples →](12-examples.md)
