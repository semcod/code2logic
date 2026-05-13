"""LLM client integrations.

Re-exports from lolm package for unified LLM management.
Backward compatible with existing code2logic imports.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from ..intent import EnhancedIntentGenerator
from ..llm_clients import (
    DEFAULT_MODELS,
    RECOMMENDED_MODELS,
    BaseLLMClient,
    LiteLLMClient,
    LLMManager,
    OllamaLocalClient,
    OpenRouterClient,
    get_client,
)


_llm_module_path = Path(__file__).resolve().parents[1] / "llm.py"
_spec = spec_from_file_location("code2logic._llm_module", _llm_module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load LLM module from {_llm_module_path}")
_llm_module = module_from_spec(_spec)
_spec.loader.exec_module(_llm_module)

CodeAnalyzer = _llm_module.CodeAnalyzer
LLMConfig = _llm_module.LLMConfig
get_available_backends = _llm_module.get_available_backends

__all__ = [
    # Core clients (from lolm)
    "BaseLLMClient",
    "OpenRouterClient",
    "OllamaLocalClient",
    "LiteLLMClient",
    "get_client",
    # Manager
    "LLMManager",
    "LLMConfig",
    # Constants
    "RECOMMENDED_MODELS",
    "DEFAULT_MODELS",
    # Intent
    "EnhancedIntentGenerator",
    # Analyzer
    "CodeAnalyzer",
    "get_available_backends",
]
