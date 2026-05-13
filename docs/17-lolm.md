## Overview

`lolm` is a reusable LLM configuration and management package that provides:

- Multi-provider support (OpenRouter, Ollama, Groq, Together, LiteLLM)
- Automatic provider fallback and priority routing
- Unified configuration via `.env` and `litellm_config.yaml`
- CLI interface similar to `reclapp llm`

## Installation

The package is included with code2logic:

```bash
pip install code2logic
```

# Show provider status
python -m lolm status

# Set default provider
python -m lolm set-provider openrouter

# Set model for provider
python -m lolm set-model openrouter nvidia/nemotron-3-nano-30b-a3b:free

# Manage API keys
python -m lolm key set openrouter YOUR_API_KEY

# List recommended models
python -m lolm models

# Test LLM generation
python -m lolm test
```

### Python API

```python
from lolm import get_client, LLMManager

# Simple usage - auto-detect provider
client = get_client()
response = client.generate("Explain this code")

# Specific provider
client = get_client(provider='openrouter')
response = client.generate("Generate a function", system="You are a code expert")

# With manager for more control
manager = LLMManager()
manager.initialize()

if manager.is_available:
    response = manager.generate("Hello!")
    print(response)
    
# With fallback
response = manager.generate_with_fallback(
    "Generate code",
    providers=['openrouter', 'groq', 'ollama']
)
```

### Environment Variables

Create a `.env` file in your project root:

```bash
# Provider API Keys
OPENROUTER_API_KEY=sk-or-v1-...
GROQ_API_KEY=gsk_...
TOGETHER_API_KEY=...

# Model overrides
OPENROUTER_MODEL=nvidia/nemotron-3-nano-30b-a3b:free
OLLAMA_MODEL=qwen2.5-coder:14b
```

### litellm_config.yaml

For advanced routing with LiteLLM:

```yaml
model_list:
  - model_name: code-analyzer
    litellm_params:
      model: ollama/qwen2.5-coder:7b
      api_base: http://localhost:11434
    priority: 10

  - model_name: general
    litellm_params:
      model: openrouter/nvidia/nemotron-3-nano-30b-a3b:free
    priority: 20

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 3
  timeout: 120
```

### User Configuration

User preferences are stored in `~/.lolm/config.json`:

```json
{
  "default_provider": "auto",
  "priority_mode": "provider-first",
  "provider_priorities": {
    "openrouter": 10,
    "ollama": 10
  },
  "provider_models": {
    "openrouter": "nvidia/nemotron-3-nano-30b-a3b:free"
  }
}
```

## CLI Reference

```
lolm status                    Show provider status
lolm set-provider PROVIDER     Set default provider
lolm set-model PROVIDER MODEL  Set model for provider
lolm key set PROVIDER KEY      Set API key
lolm key show                  Show configured keys
lolm models [PROVIDER]         List recommended models
lolm test [--provider P]       Test LLM generation
lolm config show               Show configuration
lolm priority set-provider P N Set provider priority
lolm priority set-mode MODE    Set priority mode
```

### Priority Modes

- **provider-first**: Order by provider priority (default)
- **model-first**: Order by model-specific rules
- **mixed**: Best of provider and model priorities

## Supported Providers

| Provider | Type | API Key Required | Default Model |
|----------|------|------------------|---------------|
| openrouter | Cloud | Yes | nvidia/nemotron-3-nano-30b-a3b:free |
| ollama | Local | No | qwen2.5-coder:14b |
| groq | Cloud | Yes | llama-3.1-70b-versatile |
| together | Cloud | Yes | Qwen/Qwen2.5-Coder-32B-Instruct |
| litellm | Universal | Varies | gpt-4 |

## Integration with code2logic

`lolm` is used by code2logic for:

- Intent generation (`code2logic --llm`)
- Code reproduction benchmarks
- LLM-enhanced analysis

```python
from code2logic.llm import get_client

# Uses lolm under the hood
client = get_client()
```

## Integration with logic2code

`lolm` can be used with logic2code for LLM-enhanced code generation:

```python
from logic2code import CodeGenerator, GeneratorConfig

config = GeneratorConfig(
    use_llm=True,
    llm_provider='openrouter'
)

generator = CodeGenerator('out/code2logic/project.c2l.yaml', config)
result = generator.generate('out/logic2code/generated_code/')
```

## Example Output

```
$ python -m lolm status

## LLM Provider Status

```log
Default Provider: auto
Python Engine Default: openrouter  Model: nvidia/nemotron-3-nano-30b-a3b:free

Providers:
  [10] openrouter   ✓ Available                    Model: nvidia/nemotron-3-nano-30b-a3b:free
  [10] ollama       ✓ Available                    Model: qwen2.5-coder:14b
  [15] groq         ✓ Available                    Model: llama-3.1-70b-versatile
  [30] together     ✗ Not configured               Model: Qwen/Qwen2.5-Coder-32B-Instruct
  [70] litellm      ⚠ Configured but unreachable   Model: gpt-4

Priority: lower number = tried first
```
```
