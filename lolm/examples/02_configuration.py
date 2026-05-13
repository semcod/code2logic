#!/usr/bin/env python3
"""
LOLM Configuration Example

Shows how to configure providers and manage settings.
"""

import os

from lolm import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER_PRIORITIES,
    RECOMMENDED_MODELS,
    get_config_path,
    load_config,
)


def show_defaults():
    """Show default configuration values."""
    print("=== Default Models ===")
    for provider, model in DEFAULT_MODELS.items():
        print(f"  {provider}: {model}")

    print("\n=== Default Priorities ===")
    for provider, priority in sorted(DEFAULT_PROVIDER_PRIORITIES.items(), key=lambda x: x[1]):
        print(f"  [{priority:2d}] {provider}")


def show_recommended_models():
    """Show recommended models for each provider."""
    print("\n=== Recommended Models ===")
    for provider, models in RECOMMENDED_MODELS.items():
        print(f"\n{provider}:")
        for model, description in models:
            print(f"  {model}")
            print(f"    └─ {description}")


def show_current_config():
    """Show current user configuration."""
    print("\n=== Current Configuration ===")
    print(f"Config path: {get_config_path()}")

    config = load_config()
    print(f"Default provider: {config.default_provider}")
    print(f"Priority mode: {config.priority_mode}")

    if config.provider_priorities:
        print("Provider priorities:")
        for provider, priority in config.provider_priorities.items():
            print(f"  {provider}: {priority}")

    if config.provider_models:
        print("Provider models:")
        for provider, model in config.provider_models.items():
            print(f"  {provider}: {model}")


def example_modify_config():
    """Example of modifying configuration."""
    print("\n=== Modify Configuration (Example) ===")

    # Load current config
    config = load_config()

    # Modify settings
    config.default_provider = "openrouter"
    config.provider_priorities["openrouter"] = 5
    config.provider_models["openrouter"] = "nvidia/nemotron-3-nano-30b-a3b:free"

    print("Modified config (not saved):")
    print(f"  default_provider: {config.default_provider}")
    print(f"  priorities: {config.provider_priorities}")
    print(f"  models: {config.provider_models}")

    # To save: save_config(config)
    print("\nNote: Call save_config(config) to persist changes")


def show_environment_config():
    """Show environment-based configuration."""
    print("\n=== Environment Variables ===")

    env_vars = [
        ("LLM_PROVIDER", "Default provider"),
        ("OPENROUTER_API_KEY", "OpenRouter API key"),
        ("OPENROUTER_MODEL", "OpenRouter model"),
        ("OLLAMA_HOST", "Ollama host URL"),
        ("OLLAMA_MODEL", "Ollama model"),
        ("GROQ_API_KEY", "Groq API key"),
        ("TOGETHER_API_KEY", "Together API key"),
    ]

    for var, description in env_vars:
        value = os.environ.get(var)
        if value:
            # Mask API keys
            if "KEY" in var:
                display = value[:8] + "..." if len(value) > 12 else "***"
            else:
                display = value
            print(f"  {var}: {display}")
        else:
            print(f"  {var}: (not set) - {description}")


if __name__ == "__main__":
    print("LOLM Configuration Examples\n")

    show_defaults()
    show_recommended_models()
    show_current_config()
    show_environment_config()
    example_modify_config()
