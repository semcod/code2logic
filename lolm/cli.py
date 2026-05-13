#!/usr/bin/env python3
"""
CLI interface for LOLM - LLM provider management.

Usage:
    lolm status           # Show provider status
    lolm set-provider     # Set default provider
    lolm set-model        # Set model for provider
    lolm key set          # Manage API keys
    lolm test             # Test LLM generation
    lolm models           # List recommended models
"""

import argparse
import sys
from pathlib import Path

from .config import (
    RECOMMENDED_MODELS,
    get_api_key,
    get_config_path,
    get_provider_model,
    load_config,
    save_config,
    set_api_key,
    set_provider_model,
)
from .manager import LLMManager, get_client
from .provider import LLMProviderStatus


def cmd_status(args) -> int:
    """Show LLM providers status and configuration."""
    manager = LLMManager()
    manager.initialize()

    config = load_config()

    print("\n## 🤖 LLM Configuration\n")
    print("## LLM Provider Status\n")
    print("```log")
    print(f"Default Provider: {config.default_provider}")

    if manager.primary_provider:
        primary_name = manager._primary_provider
        primary_info = manager.providers.get(primary_name)
        if primary_info:
            print(f"Python Engine Default: {primary_name}  Model: {primary_info.model}")

    print("\nProviders:")

    # Sort by priority
    sorted_providers = sorted(manager.providers.items(), key=lambda x: x[1].priority)

    for name, info in sorted_providers:
        status_icon = {
            LLMProviderStatus.AVAILABLE: "✓ Available",
            LLMProviderStatus.UNAVAILABLE: "⚠ Configured but unreachable",
            LLMProviderStatus.NOT_CONFIGURED: "✗ Not configured",
            LLMProviderStatus.ERROR: "✗ Error",
        }.get(info.status, "? Unknown")

        model_str = f"Model: {info.model}" if info.model else ""
        print(f"  [{info.priority:2d}] {name:12s} {status_icon:30s} {model_str}")

    print("\nPriority: lower number = tried first")
    print("```\n")

    return 0


def cmd_set_provider(args) -> int:
    """Set default LLM provider."""
    provider = args.provider

    valid_providers = [
        "auto",
        "openrouter",
        "ollama",
        "groq",
        "together",
        "openai",
        "anthropic",
        "litellm",
    ]
    if provider not in valid_providers:
        print(f"Error: Unknown provider '{provider}'")
        print(f"Valid providers: {', '.join(valid_providers)}")
        return 1

    config = load_config()
    config.default_provider = provider
    save_config(config)

    print(f"Default provider set to: {provider}")
    return 0


def cmd_set_model(args) -> int:
    """Set model for a specific provider."""
    provider = args.provider
    model = args.model

    set_provider_model(provider, model)
    print(f"Model for {provider} set to: {model}")
    return 0


def cmd_key_set(args) -> int:
    """Set API key for a provider."""
    provider = args.provider
    key = args.key

    env_path = Path(args.env_file) if args.env_file else Path.cwd() / ".env"

    try:
        set_api_key(provider, key, env_path)
        print(f"API key for {provider} saved to {env_path}")
        return 0
    except ValueError as e:
        print(f"Error: {e}")
        return 1


def cmd_key_show(args) -> int:
    """Show configured API keys (masked)."""
    providers = ["openrouter", "openai", "anthropic", "groq", "together"]

    print("\nConfigured API Keys:")
    for provider in providers:
        key = get_api_key(provider)
        if key:
            masked = key[:8] + "..." + key[-4:] if len(key) > 16 else "***"
            print(f"  {provider}: {masked}")
        else:
            print(f"  {provider}: (not set)")

    return 0


def cmd_models(args) -> int:
    """List recommended models for each provider."""
    provider = args.provider

    if provider and provider in RECOMMENDED_MODELS:
        print(f"\nRecommended models for {provider}:")
        for model, description in RECOMMENDED_MODELS[provider]:
            current = " (current)" if model == get_provider_model(provider) else ""
            print(f"  {model:50s} - {description}{current}")
    else:
        print("\nRecommended models by provider:\n")
        for prov, models in RECOMMENDED_MODELS.items():
            print(f"{prov}:")
            for model, description in models:
                print(f"  {model:50s} - {description}")
            print()

    return 0


def cmd_test(args) -> int:
    """Test LLM generation with a simple prompt."""
    provider = args.provider
    prompt = args.prompt or "Say 'Hello from LOLM!' in exactly 5 words."

    print("Testing LLM generation...")
    if provider:
        print(f"Provider: {provider}")

    try:
        client = get_client(provider=provider)
        print(
            f"Using: {client.provider} ({client.model if hasattr(client, 'model') else 'default'})"
        )

        response = client.generate(prompt)
        print(f"\nResponse:\n{response}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_config_show(args) -> int:
    """Show current configuration."""
    config = load_config()
    config_path = get_config_path()

    print(f"\nConfiguration file: {config_path}")
    print(f"Default provider: {config.default_provider}")
    print(f"Priority mode: {config.priority_mode}")

    if config.provider_priorities:
        print("\nProvider priorities:")
        for provider, priority in sorted(config.provider_priorities.items(), key=lambda x: x[1]):
            print(f"  {provider}: {priority}")

    if config.provider_models:
        print("\nProvider models:")
        for provider, model in config.provider_models.items():
            print(f"  {provider}: {model}")

    return 0


def cmd_priority_set_provider(args) -> int:
    """Set priority for a provider."""
    provider = args.provider
    priority = args.priority

    config = load_config()
    config.provider_priorities[provider] = priority
    save_config(config)

    print(f"Priority for {provider} set to: {priority}")
    return 0


def cmd_priority_set_mode(args) -> int:
    """Set priority mode."""
    mode = args.mode

    valid_modes = ["provider-first", "model-first", "mixed"]
    if mode not in valid_modes:
        print(f"Error: Invalid mode '{mode}'")
        print(f"Valid modes: {', '.join(valid_modes)}")
        return 1

    config = load_config()
    config.priority_mode = mode
    save_config(config)

    print(f"Priority mode set to: {mode}")
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="lolm",
        description="LOLM - Lightweight Orchestrated LLM Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # status
    status_parser = subparsers.add_parser("status", help="Show LLM providers status")
    status_parser.set_defaults(func=cmd_status)

    # set-provider
    set_provider_parser = subparsers.add_parser("set-provider", help="Set default LLM provider")
    set_provider_parser.add_argument(
        "provider", help="Provider name (auto, openrouter, ollama, etc.)"
    )
    set_provider_parser.set_defaults(func=cmd_set_provider)

    # set-model
    set_model_parser = subparsers.add_parser("set-model", help="Set model for a provider")
    set_model_parser.add_argument("provider", help="Provider name")
    set_model_parser.add_argument("model", help="Model name")
    set_model_parser.set_defaults(func=cmd_set_model)

    # key
    key_parser = subparsers.add_parser("key", help="Manage API keys")
    key_subparsers = key_parser.add_subparsers(dest="key_command")

    key_set_parser = key_subparsers.add_parser("set", help="Set API key")
    key_set_parser.add_argument("provider", help="Provider name")
    key_set_parser.add_argument("key", help="API key")
    key_set_parser.add_argument("--env-file", help="Path to .env file")
    key_set_parser.set_defaults(func=cmd_key_set)

    key_show_parser = key_subparsers.add_parser("show", help="Show configured keys")
    key_show_parser.set_defaults(func=cmd_key_show)

    # models
    models_parser = subparsers.add_parser("models", help="List recommended models")
    models_parser.add_argument("provider", nargs="?", help="Provider name (optional)")
    models_parser.set_defaults(func=cmd_models)

    # test
    test_parser = subparsers.add_parser("test", help="Test LLM generation")
    test_parser.add_argument("--provider", "-p", help="Provider to use")
    test_parser.add_argument("--prompt", help="Custom prompt")
    test_parser.set_defaults(func=cmd_test)

    # config
    config_parser = subparsers.add_parser("config", help="Show and manage configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_show_parser = config_subparsers.add_parser("show", help="Show configuration")
    config_show_parser.set_defaults(func=cmd_config_show)

    # priority
    priority_parser = subparsers.add_parser("priority", help="Manage LLM routing priorities")
    priority_subparsers = priority_parser.add_subparsers(dest="priority_command")

    priority_set_provider_parser = priority_subparsers.add_parser(
        "set-provider", help="Set provider priority"
    )
    priority_set_provider_parser.add_argument("provider", help="Provider name")
    priority_set_provider_parser.add_argument(
        "priority", type=int, help="Priority (lower = higher priority)"
    )
    priority_set_provider_parser.set_defaults(func=cmd_priority_set_provider)

    priority_set_mode_parser = priority_subparsers.add_parser("set-mode", help="Set priority mode")
    priority_set_mode_parser.add_argument("mode", help="Mode: provider-first, model-first, mixed")
    priority_set_mode_parser.set_defaults(func=cmd_priority_set_mode)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
