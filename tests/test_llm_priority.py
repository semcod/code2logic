import json
from pathlib import Path

import pytest

from code2logic.llm_clients import OpenRouterClient, OllamaLocalClient, get_client


def _write_user_llm_config(tmp_path: Path, data: dict) -> Path:
    config_dir = tmp_path / ".code2logic"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "llm_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_get_client_auto_prefers_override_provider_on_tie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Isolate user config from the real home directory
    monkeypatch.setenv("HOME", str(tmp_path))

    # Ensure we are in auto mode
    monkeypatch.setenv("CODE2LOGIC_DEFAULT_PROVIDER", "auto")

    # OpenRouter is considered configured if API key exists
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")

    # Default Ollama priority is 10. We set OpenRouter to the same priority.
    _write_user_llm_config(
        tmp_path,
        {
            "priority_mode": "provider-first",
            "provider_priorities": {"openrouter": 10},
        },
    )

    # Avoid network access
    monkeypatch.setattr(OllamaLocalClient, "is_available", lambda self: True)

    client = get_client()
    assert isinstance(client, OpenRouterClient)


def test_get_client_auto_model_first_uses_model_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODE2LOGIC_DEFAULT_PROVIDER", "auto")

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")

    # Provider defaults would choose Ollama (10) over OpenRouter (20),
    # but model-first should pick OpenRouter because the model is prioritized.
    _write_user_llm_config(
        tmp_path,
        {
            "priority_mode": "model-first",
            "model_priorities": {
                "exact": {"nvidia/nemotron-3-nano-30b-a3b:free": 5},
                "prefix": {},
            },
        },
    )

    monkeypatch.setattr(OllamaLocalClient, "is_available", lambda self: True)

    client = get_client()
    assert isinstance(client, OpenRouterClient)
