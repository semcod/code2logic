# Configuration Guide

> Setting up API keys, environment variables, and LLM providers

[← README](../README.md) | [← Back to Index](00-index.md) | [CLI Reference →](03-cli-reference.md)

## Environment Variables

Code2Logic uses environment variables for API configuration. You can set them directly or use a `.env` file.

For local development, the recommended workflow is to use the CLI to update `.env`:

```bash
code2logic llm key set openrouter <OPENROUTER_API_KEY>
code2logic llm set-model openrouter nvidia/nemotron-3-nano-30b-a3b:free
code2logic llm set-provider auto
```

# Copy example configuration
cp .env.example .env

# OpenRouter (recommended for cloud LLM)
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
export OPENROUTER_MODEL="qwen/qwen-2.5-coder-32b-instruct"

# OpenAI
export OPENAI_API_KEY="sk-your-key-here"
export OPENAI_MODEL="gpt-4-turbo"

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export ANTHROPIC_MODEL="claude-3-sonnet-20240229"

# Groq
export GROQ_API_KEY="gsk_your-key-here"
export GROQ_MODEL="llama-3.1-70b-versatile"

# Ollama (local)
export OLLAMA_HOST="http://localhost:11434"
export OLLAMA_MODEL="qwen2.5-coder:14b"

# Default provider
export CODE2LOGIC_DEFAULT_PROVIDER="ollama"

# Automatic fallback selection
export CODE2LOGIC_DEFAULT_PROVIDER="auto"
```

### Persistent Configuration

Add to your shell profile:

```bash
# ~/.bashrc or ~/.zshrc
echo 'export OPENROUTER_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc
```

## .env File

Create a `.env` file in your project root:

```env
# .env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=qwen/qwen-2.5-coder-32b-instruct

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:14b

CODE2LOGIC_DEFAULT_PROVIDER=ollama
CODE2LOGIC_VERBOSE=false
```

This `.env` file can be updated by the CLI commands:

```bash
code2logic llm set-provider auto
code2logic llm set-model openrouter nvidia/nemotron-3-nano-30b-a3b:free
code2logic llm key set openrouter <OPENROUTER_API_KEY>
```

### OpenRouter

Best for cloud-based LLM access with multiple model options.

1. Get API key: <https://openrouter.ai/keys>

2. Set environment variable:

   ```bash
   export OPENROUTER_API_KEY="sk-or-v1-..."
   ```

**Recommended Models:**

| Model | Size | Best For |
| --- | --- | --- |
| `qwen/qwen-2.5-coder-32b-instruct` | 32B | Code generation |
| `deepseek/deepseek-coder-33b-instruct` | 33B | Code analysis |
| `anthropic/claude-3-haiku` | - | Fast responses |

### Ollama (Local)

Best for local, private, and free LLM usage.

1. Install Ollama: <https://ollama.ai>

2. Pull a model:

   ```bash
   ollama pull qwen2.5-coder:14b
   ```

3. Start server:

   ```bash
   ollama serve
   ```

**Recommended Local Models:**

| Model | Size | VRAM |
| --- | --- | --- |
| `qwen2.5-coder:14b` | 14B | 10GB |
| `qwen2.5-coder:7b` | 7B | 5GB |
| `deepseek-coder:6.7b` | 6.7B | 5GB |
| `codellama:7b-instruct` | 7B | 5GB |

### OpenAI

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4-turbo"
```

### Anthropic

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-3-sonnet-20240229"
```

## Python Configuration

```python
from code2logic.config import Config

# Get API key
api_key = config.get_api_key('openrouter')

# Get model
model = config.get_model('ollama')

# Check providers
providers = config.list_configured_providers()
print(providers)
## Configuration File

Advanced users can create `~/.code2logic/config.json`.

LLM routing preferences (priority mode, provider priority overrides, model/family rules) are stored in:

- `~/.code2logic/llm_config.json`

```json
{
  "default_provider": "ollama",
  "providers": {
    "ollama": {
      "host": "http://localhost:11434",
      "model": "qwen2.5-coder:14b"
    },
    "openrouter": {
      "model": "qwen/qwen-2.5-coder-32b-instruct"
    }
  },
  "cache_enabled": true,
  "verbose": false
}
```

### API Key Not Found

```text
Error: OpenRouter API key not found
```

**Solution:** Set the environment variable or create `.env` file.

### Ollama Not Running

```text
Error: Connection refused to localhost:11434
```

**Solution:** Start Ollama server with `ollama serve`.

### Model Not Available

```text
Error: Model qwen2.5-coder:14b not found
```

**Solution:** Pull the model with `ollama pull qwen2.5-coder:14b`.

---

[← Back to Index](00-index.md) | [CLI Reference →](03-cli-reference.md)
