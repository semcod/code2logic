"""
LLM Configuration Management.

Handles loading/saving configuration from:
- Environment variables
- .env files
- litellm_config.yaml
- ~/.lolm/config.json (user preferences)
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from getv import EnvStore

    _HAS_GETV = True
except ImportError:
    _HAS_GETV = False

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# Recommended models by provider
RECOMMENDED_MODELS = {
    "openrouter": [
        ("qwen/qwen-2.5-coder-32b-instruct", "Best for code, 32B"),
        ("deepseek/deepseek-coder-33b-instruct", "DeepSeek Coder 33B"),
        ("meta-llama/llama-3.3-70b-instruct:free", "Llama 3.3 70B (free)"),
        ("nvidia/nemotron-3-nano-30b-a3b:free", "Nemotron 30B (free)"),
    ],
    "ollama": [
        ("qwen2.5-coder:14b", "Best local code model"),
        ("qwen2.5-coder:7b", "Fast local code model"),
        ("deepseek-coder:6.7b", "DeepSeek Coder"),
        ("codellama:7b-instruct", "CodeLlama 7B"),
    ],
    "groq": [
        ("llama-3.1-70b-versatile", "Llama 3.1 70B"),
        ("llama-3.1-8b-instant", "Llama 3.1 8B (fast)"),
    ],
    "together": [
        ("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B"),
        ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B"),
    ],
}

# Default models per provider
DEFAULT_MODELS = {
    "openrouter": "nvidia/nemotron-3-nano-30b-a3b:free",
    "openai": "gpt-4-turbo",
    "anthropic": "claude-3-sonnet-20240229",
    "groq": "llama-3.1-70b-versatile",
    "together": "Qwen/Qwen2.5-Coder-32B-Instruct",
    "together_ai": "gpt-4",
    "ollama": "qwen2.5-coder:14b",
    "litellm": "gpt-4",
}

# Default provider priorities (lower = higher priority)
DEFAULT_PROVIDER_PRIORITIES = {
    "openrouter": 10,
    "ollama": 10,
    "groq": 15,
    "together": 30,
    "openai": 50,
    "together_ai": 55,
    "anthropic": 60,
    "litellm": 70,
}


@dataclass
class LLMConfig:
    """LLM configuration container."""

    default_provider: str = "auto"
    priority_mode: str = "provider-first"  # provider-first, model-first, mixed
    provider_priorities: Dict[str, int] = field(default_factory=dict)
    model_priorities: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: {"exact": {}, "prefix": {}}
    )
    provider_models: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_provider": self.default_provider,
            "priority_mode": self.priority_mode,
            "provider_priorities": self.provider_priorities,
            "model_priorities": self.model_priorities,
            "provider_models": self.provider_models,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        return cls(
            default_provider=data.get("default_provider", "auto"),
            priority_mode=data.get("priority_mode", "provider-first"),
            provider_priorities=data.get("provider_priorities", {}),
            model_priorities=data.get("model_priorities", {"exact": {}, "prefix": {}}),
            provider_models=data.get("provider_models", {}),
        )


def get_config_dir() -> Path:
    """Get configuration directory path."""
    return Path.home() / ".lolm"


def get_config_path() -> Path:
    """Get user configuration file path."""
    return get_config_dir() / "config.json"


def load_config() -> LLMConfig:
    """Load configuration from file."""
    path = get_config_path()
    if not path.exists():
        return LLMConfig()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f) or {}
        return LLMConfig.from_dict(data)
    except Exception:
        return LLMConfig()


def save_config(config: LLMConfig) -> None:
    """Save configuration to file."""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def load_env_file(search_paths: Optional[List[Path]] = None) -> None:
    """Load environment variables from .env file.

    Delegates to getv.EnvStore when available.
    Also loads getv app defaults (``getv use code2logic llm PROFILE``).
    """
    # Load getv app defaults first (if configured)
    if _HAS_GETV:
        try:
            from getv import AppDefaults
            from getv.integrations.pydantic_env import load_profile_into_env

            defaults = AppDefaults("code2logic")
            llm_profile = defaults.get("llm")
            if llm_profile:
                load_profile_into_env("llm", llm_profile)
        except Exception:
            pass

    if search_paths is None:
        search_paths = [
            Path.cwd() / ".env",
            get_config_dir() / ".env",
            Path.home() / ".env",
        ]

    for path in search_paths:
        try:
            if not path.exists():
                continue
            if _HAS_GETV:
                store = EnvStore(path, auto_create=False)
                for key, value in store.items():
                    if key and value and not os.environ.get(key):
                        os.environ[key] = value
                return
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value and not os.environ.get(key):
                    os.environ[key] = value
            return
        except Exception:
            continue


def load_litellm_config(search_paths: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Load litellm_config.yaml file."""
    if not YAML_AVAILABLE:
        return {}

    if search_paths is None:
        search_paths = [
            Path.cwd() / "litellm_config.yaml",
            get_config_dir() / "litellm_config.yaml",
            Path.home() / ".lolm" / "litellm_config.yaml",
        ]

    for path in search_paths:
        try:
            if not path.exists():
                continue
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            continue

    return {}


def save_litellm_config(config: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Save litellm_config.yaml file."""
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML required: pip install pyyaml")

    if path is None:
        path = Path.cwd() / "litellm_config.yaml"

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_provider_model(provider: str) -> str:
    """Get configured model for a provider."""
    # Check environment variable first
    env_var_map = {
        "openrouter": "OPENROUTER_MODEL",
        "openai": "OPENAI_MODEL",
        "anthropic": "ANTHROPIC_MODEL",
        "groq": "GROQ_MODEL",
        "together": "TOGETHER_MODEL",
        "ollama": "OLLAMA_MODEL",
        "litellm": "LITELLM_MODEL",
    }

    env_var = env_var_map.get(provider)
    if env_var:
        value = os.environ.get(env_var)
        if value:
            return value

    # Check user config
    config = load_config()
    if provider in config.provider_models:
        return config.provider_models[provider]

    # Return default
    return DEFAULT_MODELS.get(provider, "")


def set_provider_model(provider: str, model: str) -> None:
    """Set model for a provider."""
    config = load_config()
    config.provider_models[provider] = model
    save_config(config)


def get_api_key(provider: str) -> Optional[str]:
    """Get API key for a provider."""
    env_var_map = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "together": "TOGETHER_API_KEY",
    }

    env_var = env_var_map.get(provider)
    if env_var:
        return os.environ.get(env_var)
    return None


def set_api_key(provider: str, key: str, env_path: Optional[Path] = None) -> None:
    """Set API key for a provider in .env file.

    Delegates to getv.EnvStore when available.
    """
    env_var_map = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "together": "TOGETHER_API_KEY",
    }

    env_var = env_var_map.get(provider)
    if not env_var:
        raise ValueError(f"Unknown provider: {provider}")

    if env_path is None:
        env_path = Path.cwd() / ".env"

    if _HAS_GETV:
        store = EnvStore(env_path)
        store.set(env_var, key)
        store.save()
    else:
        existing_lines = []
        if env_path.exists():
            existing_lines = env_path.read_text().splitlines()
        found = False
        new_lines = []
        for line in existing_lines:
            if line.strip().startswith(f"{env_var}="):
                new_lines.append(f"{env_var}={key}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{env_var}={key}")
        env_path.write_text("\n".join(new_lines) + "\n")

    os.environ[env_var] = key


def get_provider_priorities_from_litellm() -> Dict[str, int]:
    """Extract provider priorities from litellm_config.yaml."""
    config = load_litellm_config()
    model_list = config.get("model_list", [])

    result: Dict[str, int] = {}
    for entry in model_list:
        litellm_model = (entry.get("litellm_params") or {}).get("model", "")
        if not litellm_model:
            continue

        provider = litellm_model.split("/", 1)[0] if "/" in litellm_model else "openai"
        priority = int(entry.get("priority", 100))
        result[provider] = min(result.get(provider, 100), priority)

    return result
