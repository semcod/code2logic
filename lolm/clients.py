"""
LLM Client Implementations.

Concrete implementations for various LLM providers.
"""

import os
from typing import List

from .config import RECOMMENDED_MODELS, get_provider_model, load_env_file
from .provider import BaseLLMClient


class LLMRateLimitError(Exception):
    """Exception raised when a rate limit is hit."""

    def __init__(
        self,
        message: str,
        provider: str = "",
        status_code: int = 429,
        headers: dict = None,
        retry_after: float = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.headers = headers or {}
        self.retry_after = retry_after

    def __str__(self):
        base = super().__str__()
        if self.retry_after:
            return f"{base} (retry after {self.retry_after}s)"
        return base


# Load .env on import
load_env_file()

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


class OpenRouterClient(BaseLLMClient):
    """OpenRouter API client for cloud LLM access."""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    provider = "openrouter"

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize OpenRouter client.

        Args:
            api_key: OpenRouter API key (or set OPENROUTER_API_KEY env var)
            model: Model to use (default from config or environment)
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = model or get_provider_model("openrouter")

    def generate(self, prompt: str, system: str = None, max_tokens: int = 4000) -> str:
        """Generate completion using OpenRouter."""
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx required: pip install httpx")

        if not self.api_key:
            raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/wronai/lolm",
            "X-Title": "LOLM",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        try:
            response = httpx.post(self.API_URL, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise LLMRateLimitError(
                    "OpenRouter rate limit exceeded",
                    provider="openrouter",
                    status_code=429,
                    headers=dict(e.response.headers),
                    retry_after=float(retry_after) if retry_after else None,
                )
            error_detail = e.response.text if hasattr(e, "response") else str(e)
            raise RuntimeError(f"OpenRouter API error: {error_detail}")
        except Exception as e:
            raise RuntimeError(f"Request failed: {e}")

    def is_available(self) -> bool:
        """Check if OpenRouter is configured."""
        return bool(self.api_key)

    @staticmethod
    def list_recommended_models() -> List[tuple]:
        """List recommended models for code tasks."""
        return RECOMMENDED_MODELS.get("openrouter", [])


class OllamaClient(BaseLLMClient):
    """Ollama client for local LLM inference."""

    provider = "ollama"

    def __init__(self, model: str = None, host: str = None):
        """
        Initialize Ollama client.

        Args:
            model: Model to use (default from config or environment)
            host: Ollama host URL (default from OLLAMA_HOST or localhost:11434)
        """
        self.model = model or get_provider_model("ollama")
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def generate(self, prompt: str, system: str = None, max_tokens: int = 4000) -> str:
        """Generate completion using Ollama."""
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx required: pip install httpx")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        try:
            response = httpx.post(f"{self.host}/api/generate", json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}")

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        if not HTTPX_AVAILABLE:
            return False
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """List available Ollama models."""
        if not HTTPX_AVAILABLE:
            return []
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    @staticmethod
    def list_recommended_models() -> List[tuple]:
        """List recommended models for code tasks."""
        return RECOMMENDED_MODELS.get("ollama", [])


class LiteLLMClient(BaseLLMClient):
    """LiteLLM client for universal LLM access."""

    provider = "litellm"

    def __init__(self, model: str = None):
        """
        Initialize LiteLLM client.

        Args:
            model: Model identifier (e.g., 'ollama/qwen2.5-coder:7b', 'gpt-4')
        """
        self.model = model or get_provider_model("litellm")

    def generate(self, prompt: str, system: str = None, max_tokens: int = 4000) -> str:
        """Generate completion using LiteLLM."""
        if not LITELLM_AVAILABLE:
            raise ImportError("litellm required: pip install litellm")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = litellm.completion(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"LiteLLM error: {e}")

    def is_available(self) -> bool:
        """Check if LiteLLM is available."""
        return LITELLM_AVAILABLE


class GroqClient(BaseLLMClient):
    """Groq API client for fast inference."""

    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    provider = "groq"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model or get_provider_model("groq")

    def generate(self, prompt: str, system: str = None, max_tokens: int = 4000) -> str:
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx required: pip install httpx")

        if not self.api_key:
            raise ValueError("Groq API key not configured. Set GROQ_API_KEY.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        try:
            response = httpx.post(self.API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise LLMRateLimitError(
                    "Groq rate limit exceeded",
                    provider="groq",
                    status_code=429,
                    headers=dict(e.response.headers),
                    retry_after=float(retry_after) if retry_after else None,
                )
            raise RuntimeError(f"Groq error: {e}")
        except Exception as e:
            raise RuntimeError(f"Groq error: {e}")

    def is_available(self) -> bool:
        return bool(self.api_key)


class TogetherClient(BaseLLMClient):
    """Together AI client."""

    API_URL = "https://api.together.xyz/v1/chat/completions"
    provider = "together"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.environ.get("TOGETHER_API_KEY")
        self.model = model or get_provider_model("together")

    def generate(self, prompt: str, system: str = None, max_tokens: int = 4000) -> str:
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx required: pip install httpx")

        if not self.api_key:
            raise ValueError("Together API key not configured. Set TOGETHER_API_KEY.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        try:
            response = httpx.post(self.API_URL, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                raise LLMRateLimitError(
                    "Together rate limit exceeded",
                    provider="together",
                    status_code=429,
                    headers=dict(e.response.headers),
                    retry_after=float(retry_after) if retry_after else None,
                )
            raise RuntimeError(f"Together error: {e}")
        except Exception as e:
            raise RuntimeError(f"Together error: {e}")

    def is_available(self) -> bool:
        return bool(self.api_key)
