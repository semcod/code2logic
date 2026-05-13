#!/usr/bin/env python3
"""
LLM Configuration Script for Code2Logic.

Detects available LLM providers and models, saves configuration.

Features:
- Detects Ollama models
- Checks LiteLLM availability
- Saves config to ~/.code2logic/llm_config.json
- Tests model availability

Usage:
    python configure_llm.py              # Auto-detect and configure
    python configure_llm.py --list       # List available models
    python configure_llm.py --test       # Test configured models
    python configure_llm.py --set-default MODEL  # Set default model
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Config directory
CONFIG_DIR = Path.home() / ".code2logic"
CONFIG_FILE = CONFIG_DIR / "llm_config.json"

# Try to import optional dependencies
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


def log(msg: str, level: str = "info"):
    """Print log message with color."""
    colors = {
        "info": "\033[34m",  # Blue
        "success": "\033[32m",  # Green
        "warning": "\033[33m",  # Yellow
        "error": "\033[31m",  # Red
    }
    reset = "\033[0m"
    symbol = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}.get(level, "•")
    print(f"{colors.get(level, '')}{symbol} {msg}{reset}")


def check_ollama() -> Dict[str, Any]:
    """Check Ollama availability and get models."""
    result = {
        "available": False,
        "host": "http://localhost:11434",
        "version": None,
        "models": [],
    }

    if not HTTPX_AVAILABLE:
        return result

    try:
        # Check if Ollama is running
        response = httpx.get(f"{result['host']}/api/version", timeout=5)
        if response.status_code == 200:
            result["available"] = True
            result["version"] = response.json().get("version", "unknown")

        # Get models
        response = httpx.get(f"{result['host']}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            for model in data.get("models", []):
                result["models"].append(
                    {
                        "name": model["name"],
                        "size": model.get("size", 0),
                        "modified": model.get("modified_at", ""),
                        "family": model.get("details", {}).get("family", "unknown"),
                    }
                )
    except Exception as e:
        result["error"] = str(e)

    return result


def check_litellm() -> Dict[str, Any]:
    """Check LiteLLM availability."""
    result = {
        "available": LITELLM_AVAILABLE,
        "version": None,
        "providers": [],
    }

    if LITELLM_AVAILABLE:
        result["version"] = getattr(litellm, "__version__", "unknown")
        # List supported providers
        result["providers"] = [
            "openai",
            "anthropic",
            "ollama",
            "groq",
            "together_ai",
            "azure",
            "bedrock",
            "vertex_ai",
            "cohere",
            "huggingface",
        ]

    return result


def check_env_keys() -> Dict[str, bool]:
    """Check for API keys in environment."""
    keys = {
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
        "TOGETHER_API_KEY": bool(os.environ.get("TOGETHER_API_KEY")),
        "COHERE_API_KEY": bool(os.environ.get("COHERE_API_KEY")),
        "HUGGINGFACE_API_KEY": bool(os.environ.get("HUGGINGFACE_API_KEY")),
    }
    return keys


def categorize_models(models: List[Dict]) -> Dict[str, List[Dict]]:
    """Categorize Ollama models by type."""
    categories = {
        "code": [],
        "chat": [],
        "vision": [],
        "embedding": [],
        "other": [],
    }

    code_keywords = [
        "code",
        "coder",
        "starcoder",
        "codellama",
        "deepseek-coder",
        "devstral",
    ]
    vision_keywords = ["vision", "llava", "moondream", "bakllava"]
    embed_keywords = ["embed", "nomic"]

    for model in models:
        name_lower = model["name"].lower()

        if any(k in name_lower for k in code_keywords):
            categories["code"].append(model)
        elif any(k in name_lower for k in vision_keywords):
            categories["vision"].append(model)
        elif any(k in name_lower for k in embed_keywords):
            categories["embedding"].append(model)
        elif any(
            k in name_lower
            for k in ["instruct", "chat", "llama", "mistral", "qwen", "gemma", "phi"]
        ):
            categories["chat"].append(model)
        else:
            categories["other"].append(model)

    return categories


def get_recommended_models(models: List[Dict]) -> Dict[str, str]:
    """Get recommended models for different tasks."""
    recommendations = {
        "code_analysis": None,
        "refactoring": None,
        "documentation": None,
        "chat": None,
    }

    # Priority order for code tasks
    code_priority = [
        "qwen2.5-coder:14b",
        "qwen2.5-coder:7b",
        "deepseek-coder:6.7b",
        "codellama:7b-instruct",
        "starcoder2:15b",
        "starcoder2:7b",
    ]

    chat_priority = [
        "qwen2.5:14b",
        "qwen2.5:7b",
        "llama3.1:8b",
        "llama3:latest",
        "mistral:7b-instruct",
        "gemma3:12b",
    ]

    model_names = [m["name"] for m in models]

    for prio in code_priority:
        if prio in model_names:
            recommendations["code_analysis"] = f"ollama/{prio}"
            recommendations["refactoring"] = f"ollama/{prio}"
            break

    for prio in chat_priority:
        if prio in model_names:
            recommendations["documentation"] = f"ollama/{prio}"
            recommendations["chat"] = f"ollama/{prio}"
            break

    # Use code model as fallback for all
    if recommendations["code_analysis"]:
        for key in recommendations:
            if not recommendations[key]:
                recommendations[key] = recommendations["code_analysis"]

    return recommendations


def test_model(model: str, timeout: int = 30) -> Dict[str, Any]:
    """Test if a model works."""
    result = {
        "model": model,
        "success": False,
        "response_time": None,
        "error": None,
    }

    if model.startswith("ollama/"):
        if not HTTPX_AVAILABLE:
            result["error"] = "httpx not installed"
            return result

        model_name = model.replace("ollama/", "")
        try:
            start = time.time()
            response = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": 'Say "test ok" and nothing else.',
                    "stream": False,
                    "options": {"num_predict": 10},
                },
                timeout=timeout,
            )
            result["response_time"] = round(time.time() - start, 2)
            if response.status_code == 200:
                result["success"] = True
                result["response"] = response.json().get("response", "")[:50]
            else:
                result["error"] = f"HTTP {response.status_code}"
        except Exception as e:
            result["error"] = str(e)

    elif LITELLM_AVAILABLE:
        try:
            start = time.time()
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": "Say 'test ok'"}],
                max_tokens=10,
            )
            result["response_time"] = round(time.time() - start, 2)
            result["success"] = True
            result["response"] = response.choices[0].message.content[:50]
        except Exception as e:
            result["error"] = str(e)
    else:
        result["error"] = "No LLM client available"

    return result


def save_config(config: Dict[str, Any]):
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config["updated_at"] = datetime.now().isoformat()

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    log(f"Config saved to: {CONFIG_FILE}", "success")


def load_config() -> Dict[str, Any]:
    """Load configuration from file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def format_size(size_bytes: int) -> str:
    """Format size in human readable form."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def main():
    """Main entry point."""
    args = sys.argv[1:]

    print("=" * 60)
    print("CODE2LOGIC LLM CONFIGURATION")
    print("=" * 60)

    # List models only
    if "--list" in args:
        ollama = check_ollama()
        if ollama["available"]:
            print(f"\nOllama Models ({len(ollama['models'])} available):")
            categories = categorize_models(ollama["models"])

            for cat, models in categories.items():
                if models:
                    print(f"\n  {cat.upper()}:")
                    for m in sorted(models, key=lambda x: -x["size"]):
                        size = format_size(m["size"])
                        print(f"    ollama/{m['name']:<35} ({size})")
        else:
            log("Ollama not running", "warning")

        env_keys = check_env_keys()
        configured = [k for k, v in env_keys.items() if v]
        if configured:
            print(f"\nAPI Keys configured: {', '.join(configured)}")

        sys.exit(0)

    # Test models
    if "--test" in args:
        config = load_config()
        if not config:
            log("No config found. Run without --test first.", "error")
            sys.exit(1)

        print("\nTesting configured models...")
        for task, model in config.get("recommendations", {}).items():
            if model:
                result = test_model(model, timeout=30)
                if result["success"]:
                    log(f"{task}: {model} ({result['response_time']}s)", "success")
                else:
                    log(f"{task}: {model} - {result['error']}", "error")
        sys.exit(0)

    # Set default model
    if "--set-default" in args:
        idx = args.index("--set-default")
        if idx + 1 >= len(args):
            log("Usage: --set-default MODEL", "error")
            sys.exit(1)

        model = args[idx + 1]
        config = load_config()
        config["default_model"] = model
        save_config(config)
        log(f"Default model set to: {model}", "success")
        sys.exit(0)

    # Full detection
    print("\nDetecting available LLM providers...")

    config = {
        "ollama": {},
        "litellm": {},
        "api_keys": {},
        "recommendations": {},
        "default_model": None,
    }

    # Check Ollama
    print("\n" + "-" * 40)
    print("OLLAMA")
    print("-" * 40)

    ollama = check_ollama()
    config["ollama"] = {
        "available": ollama["available"],
        "host": ollama["host"],
        "version": ollama.get("version"),
        "model_count": len(ollama["models"]),
    }

    if ollama["available"]:
        log(f"Ollama {ollama['version']} running at {ollama['host']}", "success")
        log(f"Found {len(ollama['models'])} models", "info")

        categories = categorize_models(ollama["models"])
        for cat, models in categories.items():
            if models:
                print(f"  {cat}: {len(models)} models")

        # Save model list
        config["ollama"]["models"] = [m["name"] for m in ollama["models"]]
    else:
        log("Ollama not running or not installed", "warning")
        print("  Start with: ollama serve")
        print("  Install from: https://ollama.ai")

    # Check LiteLLM
    print("\n" + "-" * 40)
    print("LITELLM")
    print("-" * 40)

    litellm_info = check_litellm()
    config["litellm"] = {
        "available": litellm_info["available"],
        "version": litellm_info.get("version"),
    }

    if litellm_info["available"]:
        log(f"LiteLLM {litellm_info['version']} installed", "success")
        print(f"  Supported providers: {', '.join(litellm_info['providers'][:5])}...")
    else:
        log("LiteLLM not installed", "warning")
        print("  Install with: pip install litellm")

    # Check API Keys
    print("\n" + "-" * 40)
    print("API KEYS")
    print("-" * 40)

    env_keys = check_env_keys()
    config["api_keys"] = env_keys

    for key, available in env_keys.items():
        if available:
            log(f"{key} configured", "success")
        else:
            print(f"  {key}: not set")

    # Recommendations
    print("\n" + "-" * 40)
    print("RECOMMENDED MODELS")
    print("-" * 40)

    if ollama["models"]:
        recommendations = get_recommended_models(ollama["models"])
        config["recommendations"] = recommendations

        for task, model in recommendations.items():
            if model:
                log(f"{task}: {model}", "info")

        # Set default
        config["default_model"] = recommendations.get(
            "code_analysis"
        ) or recommendations.get("chat")
        if config["default_model"]:
            log(f"Default model: {config['default_model']}", "success")
    else:
        log("No models available for recommendations", "warning")
        print("  Pull models with: ollama pull qwen2.5-coder:7b")

    # Save config
    save_config(config)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    status = []
    if ollama["available"]:
        status.append(f"Ollama: {len(ollama['models'])} models")
    if litellm_info["available"]:
        status.append("LiteLLM: ready")
    configured_keys = sum(1 for v in env_keys.values() if v)
    if configured_keys:
        status.append(f"API Keys: {configured_keys}")

    print(f"  {' | '.join(status)}")

    if config["default_model"]:
        print(f"\n  Ready to use! Default model: {config['default_model']}")
    else:
        print("\n  ⚠️  No models available. Install Ollama or set API keys.")


if __name__ == "__main__":
    main()
