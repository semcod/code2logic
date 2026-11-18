"""
LOLM - Lightweight Orchestrated LLM Manager

A reusable LLM configuration and management package for Python projects.
Supports multiple providers with automatic fallback, priority routing,
and unified configuration via .env and litellm_config.yaml.

Supported Providers:
- OpenRouter (cloud, multiple models)
- Ollama (local inference)
- OpenAI, Anthropic, Groq, Together (cloud)
- LiteLLM (universal interface)

Usage:
    from lolm import get_client, LLMManager

    # Simple usage
    client = get_client()
    response = client.generate("Explain this code")

    # With manager
    manager = LLMManager()
    await manager.initialize()
    response = await manager.generate(GenerateOptions(
        system="You are a code generator",
        user="Create a function to add two numbers"
    ))

CLI:
    lolm status           # Show provider status
    lolm set-provider     # Set default provider
    lolm key set          # Manage API keys
    lolm test             # Test LLM generation
"""

from .clients import (
    LiteLLMClient,
    LLMRateLimitError,
    OllamaClient,
    OpenRouterClient,
)
from .config import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER_PRIORITIES,
    RECOMMENDED_MODELS,
    LLMConfig,
    get_config_path,
    get_provider_model,
    get_provider_priorities_from_litellm,
    load_config,
    save_config,
)
from .manager import (
    LLMManager,
    ProviderInfo,
    get_client,
    list_available_providers,
)
from .provider import (
    BaseLLMClient,
    GenerateOptions,
    LLMModelInfo,
    LLMProvider,
    LLMProviderStatus,
    LLMResponse,
)
from .rotation import (
    LLMRotationManager,
    ProviderHealth,
    ProviderState,
    RateLimitInfo,
    RateLimitType,
    RotationQueue,
    create_rotation_manager,
    is_rate_limit_error,
    parse_rate_limit_headers,
)

def _resolve_version() -> str:
    """Installed metadata first; a source checkout reads the sibling pyproject.toml."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("lolm")
    except PackageNotFoundError:
        import re
        from pathlib import Path
        pyproject = Path(__file__).resolve().with_name("pyproject.toml")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M) if pyproject.is_file() else None
        return match.group(1) if match else "0+unknown"


__version__ = _resolve_version()
__all__ = [
    # Config
    "LLMConfig",
    "load_config",
    "save_config",
    "get_config_path",
    "get_provider_model",
    "get_provider_priorities_from_litellm",
    "DEFAULT_MODELS",
    "DEFAULT_PROVIDER_PRIORITIES",
    "RECOMMENDED_MODELS",
    # Provider base
    "BaseLLMClient",
    "LLMProvider",
    "LLMProviderStatus",
    "LLMResponse",
    "LLMModelInfo",
    "GenerateOptions",
    # Clients
    "OpenRouterClient",
    "OllamaClient",
    "LiteLLMClient",
    # Manager
    "LLMManager",
    "ProviderInfo",
    "get_client",
    "list_available_providers",
    # Rotation
    "RotationQueue",
    "ProviderHealth",
    "ProviderState",
    "RateLimitInfo",
    "RateLimitType",
    "LLMRotationManager",
    "LLMRateLimitError",
    "parse_rate_limit_headers",
    "is_rate_limit_error",
    "create_rotation_manager",
]
