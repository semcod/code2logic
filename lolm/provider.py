"""
LLM Provider Base Classes and Types.

Abstract base classes and data types for LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class LLMProviderStatus(str, Enum):
    """Provider availability status."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"


@dataclass
class GenerateOptions:
    """Options for LLM generation."""

    system: str = ""
    user: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    response_format: Literal["json", "text"] = "text"
    stop: Optional[List[str]] = None

    def to_messages(self) -> List[Dict[str, str]]:
        """Convert to messages format."""
        messages = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        if self.user:
            messages.append({"role": "user", "content": self.user})
        return messages


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    content: str
    model: str
    provider: str
    tokens_used: int = 0
    duration_ms: int = 0
    raw: Optional[Dict[str, Any]] = None


@dataclass
class LLMModelInfo:
    """Information about an available model."""

    name: str
    size: Optional[str] = None
    modified: Optional[str] = None
    is_code_model: bool = False
    description: Optional[str] = None


class BaseLLMClient(ABC):
    """Abstract base class for synchronous LLM clients."""

    provider: str = "unknown"

    @abstractmethod
    def generate(self, prompt: str, system: str = None, max_tokens: int = 4000) -> str:
        """Generate completion."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if client is available."""
        pass

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 4000) -> str:
        """Chat completion (default implementation)."""
        prompt_parts = []
        system = None
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                prompt_parts.append(f"{msg['role']}: {msg['content']}")
        return self.generate("\n".join(prompt_parts), system=system, max_tokens=max_tokens)


class LLMProvider(ABC):
    """
    Abstract base class for async LLM providers.

    Implementations must provide:
    - is_available(): Check if provider is accessible
    - list_models(): List available models
    - generate(): Generate completion
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """Current model name."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is available."""
        pass

    @abstractmethod
    async def list_models(self) -> List[LLMModelInfo]:
        """List available models."""
        pass

    @abstractmethod
    async def generate(self, options: GenerateOptions) -> LLMResponse:
        """Generate completion."""
        pass

    async def has_model(self, model_name: str) -> bool:
        """Check if specific model is available."""
        models = await self.list_models()
        model_base = model_name.split(":")[0]
        return any(m.name == model_name or m.name.startswith(f"{model_base}:") for m in models)

    def get_code_models(self, models: List[LLMModelInfo]) -> List[LLMModelInfo]:
        """Filter models suitable for code generation."""
        code_keywords = ["code", "coder", "codellama", "deepseek", "qwen", "starcoder"]
        return [m for m in models if any(kw in m.name.lower() for kw in code_keywords)]

    async def close(self) -> None:
        """Close provider connection."""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
