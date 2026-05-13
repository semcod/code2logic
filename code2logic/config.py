"""
Configuration management for Code2Logic.

Supports loading API keys and settings from:
1. Environment variables
2. .env file
3. ~/.code2logic/config.json
4. Command line arguments

Usage:
    from code2logic.config import Config

    config = Config()
    api_key = config.get_api_key('openrouter')
    model = config.get_model('openrouter')
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Configuration manager for Code2Logic."""

    # Default models for each provider (optimized for code tasks, <32B)
    DEFAULT_MODELS = {
        "openrouter": "qwen/qwen-2.5-coder-32b-instruct",
        "openai": "gpt-4-turbo",
        "anthropic": "claude-3-sonnet-20240229",
        "groq": "llama-3.1-70b-versatile",
        "together": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "ollama": "qwen2.5-coder:14b",
    }

    # API key environment variable names
    API_KEY_VARS = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "together": "TOGETHER_API_KEY",
    }

    # Model environment variable names
    MODEL_VARS = {
        "openrouter": "OPENROUTER_MODEL",
        "openai": "OPENAI_MODEL",
        "anthropic": "ANTHROPIC_MODEL",
        "groq": "GROQ_MODEL",
        "together": "TOGETHER_MODEL",
        "ollama": "OLLAMA_MODEL",
    }

    def __init__(self, env_file: str = None):
        """Initialize configuration.

        Args:
            env_file: Path to .env file (default: .env in current dir or project root)
        """
        self._config: Dict[str, Any] = {}
        self._load_env_file(env_file)
        self._load_config_file()

    def _load_env_file(self, env_file: str = None):
        """Load environment variables from .env file."""
        # Try multiple locations
        env_paths = [
            env_file,
            Path.cwd() / ".env",
            Path(__file__).parent.parent / ".env",
            Path.home() / ".code2logic" / ".env",
        ]

        for env_path in env_paths:
            if env_path and Path(env_path).exists():
                self._parse_env_file(Path(env_path))
                break

    def _parse_env_file(self, path: Path):
        """Parse .env file and set environment variables."""
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value and not os.environ.get(key):
                            os.environ[key] = value
        except Exception:
            pass

    def _load_config_file(self):
        """Load configuration from JSON file."""
        config_path = Path.home() / ".code2logic" / "llm_config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    self._config = json.load(f)
            except Exception:
                pass

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider.

        Args:
            provider: Provider name (openrouter, openai, anthropic, groq, together)

        Returns:
            API key or None if not configured
        """
        var_name = self.API_KEY_VARS.get(provider)
        if var_name:
            return os.environ.get(var_name)
        return None

    def get_model(self, provider: str) -> str:
        """Get model for a provider.

        Args:
            provider: Provider name

        Returns:
            Model name
        """
        # Check environment variable first
        var_name = self.MODEL_VARS.get(provider)
        if var_name:
            env_model = os.environ.get(var_name)
            if env_model:
                return env_model

        # Check config file
        recommendations = self._config.get("recommendations", {})
        if provider == "ollama" and recommendations.get("code_analysis"):
            return recommendations["code_analysis"].replace("ollama/", "")

        # Return default
        return self.DEFAULT_MODELS.get(provider, "gpt-4")

    def get_ollama_host(self) -> str:
        """Get Ollama host URL."""
        return os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def get_default_provider(self) -> str:
        """Get default LLM provider."""
        return os.environ.get("CODE2LOGIC_DEFAULT_PROVIDER", "ollama")

    def is_verbose(self) -> bool:
        """Check if verbose mode is enabled."""
        return os.environ.get("CODE2LOGIC_VERBOSE", "").lower() in ("true", "1", "yes")

    def get_project_name(self) -> str:
        """Get default project name for output files.

        Returns:
            Project name (default: 'project')
        """
        return os.environ.get("CODE2LOGIC_PROJECT_NAME", "project")

    def get_cache_dir(self) -> Path:
        """Get cache directory path."""
        cache_dir = os.environ.get("CODE2LOGIC_CACHE_DIR", "~/.code2logic/cache")
        return Path(cache_dir).expanduser()

    def list_configured_providers(self) -> Dict[str, bool]:
        """List all providers and their configuration status."""
        result = {}
        for provider in self.API_KEY_VARS:
            result[provider] = bool(self.get_api_key(provider))

        # Check Ollama separately (no API key needed)
        result["ollama"] = self._config.get("ollama", {}).get("available", False)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return {
            "providers": self.list_configured_providers(),
            "default_provider": self.get_default_provider(),
            "models": {p: self.get_model(p) for p in self.DEFAULT_MODELS},
            "ollama_host": self.get_ollama_host(),
            "verbose": self.is_verbose(),
            "cache_dir": str(self.get_cache_dir()),
        }


def load_env():
    """Load environment variables from .env file.

    Call this at the start of your script to ensure .env is loaded.
    """
    Config()


def get_api_key(provider: str) -> Optional[str]:
    """Convenience function to get API key."""
    return Config().get_api_key(provider)


def get_model(provider: str) -> str:
    """Convenience function to get model."""
    return Config().get_model(provider)


# Shell commands for configuration
SHELL_COMMANDS = """
# =============================================================================
# Code2Logic API Configuration Commands
# =============================================================================

# Set OpenRouter API key
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# Set OpenAI API key
export OPENAI_API_KEY="sk-your-key-here"

# Set Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Set Groq API key
export GROQ_API_KEY="gsk_your-key-here"

# Set Together AI API key
export TOGETHER_API_KEY="your-key-here"

# Set default provider
export CODE2LOGIC_DEFAULT_PROVIDER="openrouter"

# Set custom model
export OPENROUTER_MODEL="qwen/qwen-2.5-coder-32b-instruct"

# Or add to your shell profile (~/.bashrc, ~/.zshrc):
# echo 'export OPENROUTER_API_KEY="your-key"' >> ~/.bashrc
# source ~/.bashrc
"""


if __name__ == "__main__":
    print(SHELL_COMMANDS)
    print("\nCurrent configuration:")
    config = Config()
    import json

    print(json.dumps(config.to_dict(), indent=2))
