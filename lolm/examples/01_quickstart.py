#!/usr/bin/env python3
"""
LOLM Quickstart Example

Basic usage of lolm for LLM interactions.
"""

from lolm import LLMManager, get_client


def example_simple_client():
    """Simple client usage - auto-detect provider."""
    print("=== Simple Client ===")

    # Get client (auto-detects available provider)
    client = get_client()
    print(f"Using provider: {client.provider}")

    # Generate response
    response = client.generate(
        "What is 2 + 2? Answer with just the number.",
        system="You are a helpful assistant. Be concise.",
    )
    print(f"Response: {response}")


def example_specific_provider():
    """Use a specific provider."""
    print("\n=== Specific Provider ===")

    # Explicitly use openrouter
    try:
        client = get_client(provider="openrouter")
        print(f"Using: {client.provider} with model {client.model}")

        response = client.generate("Say hello in Python code")
        print(f"Response: {response[:200]}...")
    except Exception as e:
        print(f"OpenRouter not available: {e}")


def example_manager():
    """Use LLMManager for more control."""
    print("\n=== LLM Manager ===")

    manager = LLMManager()
    manager.initialize()

    # Show status
    print(f"Available: {manager.is_available}")
    print(f"Primary provider: {manager._primary_provider}")

    # Show all providers
    print("\nProviders:")
    for name, info in manager.providers.items():
        print(f"  {name}: {info.status.value} (priority: {info.priority})")

    # Generate with fallback
    if manager.is_available:
        response = manager.generate(
            "What programming language is this: print('hello')?", system="Answer in one word."
        )
        print(f"\nResponse: {response}")


def example_fallback():
    """Use fallback between providers."""
    print("\n=== Fallback Example ===")

    manager = LLMManager()
    manager.initialize()

    try:
        # Try multiple providers in order
        response = manager.generate_with_fallback(
            "Name 3 programming languages. Be brief.", providers=["openrouter", "groq", "ollama"]
        )
        print(f"Response: {response}")
    except RuntimeError as e:
        print(f"All providers failed: {e}")


if __name__ == "__main__":
    print("LOLM Quickstart Examples\n")

    example_simple_client()
    example_specific_provider()
    example_manager()
    example_fallback()
