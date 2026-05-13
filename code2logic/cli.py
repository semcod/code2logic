"""
Command-line interface for Code2Logic.

Usage:
    code2logic /path/to/project
    code2logic /path/to/project -f csv -o output.csv
    code2logic /path/to/project -f yaml
    code2logic /path/to/project -f json --flat
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

from . import __version__

CONSTANT_3 = 3
CONSTANT_4 = 4
CONSTANT_5 = 5
CONSTANT_50 = 50
CONSTANT_60 = 60


CONSTANT_3 = CONSTANT_3
CONSTANT_4 = CONSTANT_4
CONSTANT_5 = CONSTANT_5
CONSTANT_50 = CONSTANT_50
CONSTANT_60 = CONSTANT_60


CONSTANT_3 = CONSTANT_3
CONSTANT_4 = CONSTANT_4
CONSTANT_5 = CONSTANT_5
CONSTANT_50 = CONSTANT_50
CONSTANT_60 = CONSTANT_60


CONSTANT_3 = CONSTANT_3
CONSTANT_4 = CONSTANT_4
CONSTANT_5 = CONSTANT_5
CONSTANT_50 = CONSTANT_50
CONSTANT_60 = CONSTANT_60


# Colors for terminal output
class Colors:
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    NC = "\033[0m"  # No Color


class Logger:
    """Enhanced logger for CLI output."""

    def __init__(self, verbose: bool = False, debug: bool = False):
        self.verbose = verbose
        self.debug = debug
        self.start_time = time.time()
        self._step = 0

    def _elapsed(self) -> str:
        """Get elapsed time string."""
        elapsed = time.time() - self.start_time
        return f"{elapsed:.2f}s"

    def info(self, msg: str):
        """Print info message."""
        print(f"{Colors.BLUE}ℹ{Colors.NC} {msg}", file=sys.stderr)

    def success(self, msg: str):
        """Print success message."""
        print(f"{Colors.GREEN}✓{Colors.NC} {msg}", file=sys.stderr)

    def warning(self, msg: str):
        """Print warning message."""
        print(f"{Colors.YELLOW}⚠{Colors.NC} {msg}", file=sys.stderr)

    def error(self, msg: str):
        """Print error message."""
        print(f"{Colors.RED}✗{Colors.NC} {msg}", file=sys.stderr)

    def step(self, msg: str):
        """Print step message with counter."""
        self._step += 1
        if self.verbose:
            print(
                f"{Colors.CYAN}[{self._step}]{Colors.NC} {msg} {Colors.DIM}({self._elapsed()}){Colors.NC}",
                file=sys.stderr,
            )

    def detail(self, msg: str):
        """Print detail message (only in verbose mode)."""
        if self.verbose:
            print(f"    {Colors.DIM}{msg}{Colors.NC}", file=sys.stderr)

    def debug_msg(self, msg: str):
        """Print debug message (only in debug mode)."""
        if self.debug:
            print(f"{Colors.DIM}[DEBUG] {msg}{Colors.NC}", file=sys.stderr)

    def stats(self, label: str, value):
        """Print statistics."""
        if self.verbose:
            print(f"    {Colors.BOLD}{label}:{Colors.NC} {value}", file=sys.stderr)

    def separator(self):
        """Print separator line."""
        if self.verbose:
            print(f"{Colors.DIM}{'─' * CONSTANT_50}{Colors.NC}", file=sys.stderr)

    def header(self, msg: str):
        """Print header."""
        if self.verbose:
            print(f"\n{Colors.BOLD}{Colors.BLUE}{msg}{Colors.NC}", file=sys.stderr)
            print(f"{Colors.DIM}{'═' * len(msg)}{Colors.NC}", file=sys.stderr)


def ensure_dependencies():
    """Auto-install optional dependencies for best results."""
    packages = {
        "tree-sitter": "tree_sitter",
        "tree-sitter-python": "tree_sitter_python",
        "tree-sitter-javascript": "tree_sitter_javascript",
        "tree-sitter-typescript": "tree_sitter_typescript",
        "networkx": "networkx",
        "rapidfuzz": "rapidfuzz",
        "pyyaml": "yaml",
    }

    missing = []
    for pkg_name, import_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print(
            f"Installing dependencies for best results: {', '.join(missing)}",
            file=sys.stderr,
        )
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-q",
                    "--break-system-packages",
                    *missing,
                ],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
            print("Dependencies installed successfully!", file=sys.stderr)
        except subprocess.CalledProcessError:
            # Try without --break-system-packages
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-q", *missing],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
                print("Dependencies installed successfully!", file=sys.stderr)
            except subprocess.CalledProcessError:
                print(
                    f"Warning: Could not install some dependencies. "
                    f"Install manually: pip install {' '.join(missing)}",
                    file=sys.stderr,
                )


def _get_env_file_path() -> str:
    return os.path.join(os.getcwd(), ".env")


def _read_text_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _write_text_file(path: str, content: str) -> None:
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _set_env_var(var_name: str, value: str) -> str:
    env_path = _get_env_file_path()
    content = _read_text_file(env_path)

    import re

    if re.search(rf"^{re.escape(var_name)}=", content, re.MULTILINE):
        content = re.sub(
            rf"^{re.escape(var_name)}=.*$",
            f"{var_name}={value}",
            content,
            flags=re.MULTILINE,
        )
    elif re.search(rf"^#\s*{re.escape(var_name)}=", content, re.MULTILINE):
        content = re.sub(
            rf"^#\s*{re.escape(var_name)}=.*$",
            f"{var_name}={value}",
            content,
            flags=re.MULTILINE,
        )
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{var_name}={value}\n"

    _write_text_file(env_path, content)
    return env_path


def _unset_env_var(var_name: str) -> str:
    env_path = _get_env_file_path()
    content = _read_text_file(env_path)
    if not content:
        return env_path

    lines = content.splitlines(True)
    new_lines = [ln for ln in lines if not ln.startswith(f"{var_name}=")]
    _write_text_file(env_path, "".join(new_lines))
    return env_path


def _get_litellm_config_path() -> str:
    return os.path.join(os.getcwd(), "litellm_config.yaml")


def _get_user_llm_config_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".code2logic", "llm_config.json")


def _load_user_llm_config() -> dict:
    path = _get_user_llm_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_user_llm_config(data: dict) -> str:
    path = _get_user_llm_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
    return path


def _load_litellm_yaml() -> dict:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "pyyaml is required for this command. Install: pip install pyyaml"
        ) from e

    path = _get_litellm_config_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"litellm_config.yaml not found at {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if data.get("model_list") is None:
        data["model_list"] = []
    if data.get("router_settings") is None:
        data["router_settings"] = {}
    return data


def _save_litellm_yaml(data: dict) -> str:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "pyyaml is required for this command. Install: pip install pyyaml"
        ) from e

    path = _get_litellm_config_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return path


def _infer_provider_from_litellm_model(litellm_model: str) -> str:
    if not litellm_model:
        return ""
    if "/" not in litellm_model:
        return "openai"
    return litellm_model.split("/", 1)[0]


def _code2logic_llm_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="code2logic llm",
        description="Manage Code2Logic LLM configuration (providers, keys, priorities)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show LLM provider status and effective priorities")

    p_config = sub.add_parser("config", help="Manage litellm_config.yaml")
    config_sub = p_config.add_subparsers(dest="config_cmd", required=True)
    config_sub.add_parser("list", help="Print litellm_config.yaml as JSON")

    p_set_provider = sub.add_parser("set-provider", help="Set default provider")
    p_set_provider.add_argument(
        "provider",
        choices=[
            "openrouter",
            "ollama",
            "litellm",
            "openai",
            "anthropic",
            "groq",
            "together",
            "auto",
        ],
    )

    p_set_model = sub.add_parser("set-model", help="Set model for a provider")
    p_set_model.add_argument(
        "provider",
        choices=[
            "openrouter",
            "ollama",
            "litellm",
            "openai",
            "anthropic",
            "groq",
            "together",
        ],
    )
    p_set_model.add_argument("model")

    p_key = sub.add_parser("key", help="Manage provider API keys (.env)")
    key_sub = p_key.add_subparsers(dest="key_cmd", required=True)
    p_key_set = key_sub.add_parser("set", help="Set provider API key in .env")
    p_key_set.add_argument(
        "provider", choices=["openrouter", "openai", "anthropic", "groq", "together"]
    )
    p_key_set.add_argument("api_key")
    p_key_unset = key_sub.add_parser("unset", help="Remove provider API key from .env")
    p_key_unset.add_argument(
        "provider", choices=["openrouter", "openai", "anthropic", "groq", "together"]
    )

    p_priority = sub.add_parser(
        "priority", help="Manage routing priorities in litellm_config.yaml"
    )
    pr_sub = p_priority.add_subparsers(dest="priority_cmd", required=True)

    p_pr_mode = pr_sub.add_parser(
        "set-mode", help="Set priority mode (provider-first, model-first, mixed)"
    )
    p_pr_mode.add_argument("mode", choices=["provider-first", "model-first", "mixed"])

    p_pr_provider = pr_sub.add_parser(
        "set-provider", help="Set priority for all models of a provider"
    )
    p_pr_provider.add_argument(
        "provider",
        choices=[
            "ollama",
            "openrouter",
            "openai",
            "anthropic",
            "groq",
            "together",
            "litellm",
        ],
    )
    p_pr_provider.add_argument("priority", type=int)
    p_pr_provider.add_argument("--preserve-order", action="store_true")
    p_pr_provider.add_argument("--step", type=int, default=CONSTANT_5)

    p_pr_model = pr_sub.add_parser(
        "set-model", help="Set priority for one model_name entry"
    )
    p_pr_model.add_argument("model_name")
    p_pr_model.add_argument("priority", type=int)

    p_pr_llm_model = pr_sub.add_parser(
        "set-llm-model",
        help="Set priority for a specific LLM model string (independent of provider)",
    )
    p_pr_llm_model.add_argument("model")
    p_pr_llm_model.add_argument("priority", type=int)

    p_pr_llm_family = pr_sub.add_parser(
        "set-llm-family",
        help="Set priority for a family/prefix of LLM models (independent of provider)",
    )
    p_pr_llm_family.add_argument("prefix")
    p_pr_llm_family.add_argument("priority", type=int)

    args = parser.parse_args(argv)

    if args.cmd == "set-provider":
        env_path = _set_env_var("CODE2LOGIC_DEFAULT_PROVIDER", args.provider)
        print(f"✓ Default provider set to: {args.provider}")
        print(f"Updated: {env_path}")
        return

    if args.cmd == "set-model":
        var_map = {
            "openrouter": "OPENROUTER_MODEL",
            "openai": "OPENAI_MODEL",
            "anthropic": "ANTHROPIC_MODEL",
            "groq": "GROQ_MODEL",
            "together": "TOGETHER_MODEL",
            "ollama": "OLLAMA_MODEL",
            "litellm": "LITELLM_MODEL",
        }
        env_path = _set_env_var(var_map[args.provider], args.model)
        print(f"✓ {args.provider} model set to: {args.model}")
        print(f"Updated: {env_path}")
        return

    if args.cmd == "key":
        key_var_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "groq": "GROQ_API_KEY",
            "together": "TOGETHER_API_KEY",
        }
        var_name = key_var_map[args.provider]
        if args.key_cmd == "set":
            env_path = _set_env_var(var_name, args.api_key)
            print(f"✓ API key set for: {args.provider}")
            print(f"Updated: {env_path}")
            return
        if args.key_cmd == "unset":
            env_path = _unset_env_var(var_name)
            print(f"✓ API key removed for: {args.provider}")
            print(f"Updated: {env_path}")
            return

    if args.cmd == "config" and args.config_cmd == "list":
        data = _load_litellm_yaml()
        print(json.dumps(data, indent=2, sort_keys=False))
        return

    if args.cmd == "priority":
        data = _load_litellm_yaml()
        model_list = data.get("model_list", [])

        if args.priority_cmd == "set-mode":
            cfg = _load_user_llm_config()
            cfg["priority_mode"] = args.mode
            path = _save_user_llm_config(cfg)
            print(f"✓ Priority mode set to: {args.mode}")
            print(f"Updated: {path}")
            return

        if args.priority_cmd == "set-provider":
            matched = []
            for entry in model_list:
                litellm_model = (entry.get("litellm_params") or {}).get("model") or ""
                entry_provider = _infer_provider_from_litellm_model(litellm_model)
                if entry_provider == args.provider:
                    matched.append(entry)

            # Always persist provider-level priority, even if YAML has no entries for that provider.
            user_cfg = _load_user_llm_config()
            user_cfg.setdefault("provider_priorities", {})
            user_cfg["provider_priorities"][args.provider] = int(args.priority)
            user_cfg_path = _save_user_llm_config(user_cfg)

            if args.preserve_order:
                matched_sorted = sorted(
                    matched, key=lambda e: int(e.get("priority", 100))
                )
                for idx, entry in enumerate(matched_sorted):
                    entry["priority"] = int(args.priority) + idx * int(args.step)
            else:
                for entry in matched:
                    entry["priority"] = int(args.priority)

            if matched:
                path = _save_litellm_yaml(data)
                print(
                    f"✓ Set provider priority: {args.provider} -> {args.priority} ({len(matched)} model(s))"
                )
                print(f"Updated: {path}")
            else:
                print(
                    f"✓ Set provider priority: {args.provider} -> {args.priority} (no YAML models matched)"
                )
            print(f"Updated: {user_cfg_path}")
            return

        if args.priority_cmd == "set-model":
            matched = False
            for entry in model_list:
                if entry.get("model_name") == args.model_name:
                    entry["priority"] = int(args.priority)
                    matched = True
                    break
            if not matched:
                print(f"⚠ model_name not found: {args.model_name}")
                return
            path = _save_litellm_yaml(data)
            print(f"✓ Set model priority: {args.model_name} -> {args.priority}")
            print(f"Updated: {path}")
            return

        if args.priority_cmd == "set-llm-model":
            cfg = _load_user_llm_config()
            cfg.setdefault("model_priorities", {})
            cfg["model_priorities"].setdefault("exact", {})
            cfg["model_priorities"]["exact"][args.model] = int(args.priority)
            path = _save_user_llm_config(cfg)
            print(f"✓ Set LLM model priority: {args.model} -> {args.priority}")
            print(f"Updated: {path}")
            return

        if args.priority_cmd == "set-llm-family":
            cfg = _load_user_llm_config()
            cfg.setdefault("model_priorities", {})
            cfg["model_priorities"].setdefault("prefix", {})
            cfg["model_priorities"]["prefix"][args.prefix] = int(args.priority)
            path = _save_user_llm_config(cfg)
            print(f"✓ Set LLM family priority: {args.prefix} -> {args.priority}")
            print(f"Updated: {path}")
            return

    if args.cmd == "status":
        from .config import Config
        from .llm_clients import (
            OllamaLocalClient,
            OpenRouterClient,
            get_effective_provider_priorities,
            get_priority_mode,
        )

        cfg = Config()
        default_provider = cfg.get_default_provider()
        configured = cfg.list_configured_providers()

        priority_mode = get_priority_mode()
        priorities = get_effective_provider_priorities()

        available = {}
        try:
            available["ollama"] = OllamaLocalClient().is_available()
        except Exception:
            available["ollama"] = False

        try:
            available["openrouter"] = OpenRouterClient().is_available()
        except Exception:
            available["openrouter"] = False

        try:
            from .llm_clients import LiteLLMClient

            available["litellm"] = LiteLLMClient().is_available()
        except Exception:
            available["litellm"] = False

        for p in ["openai", "anthropic", "groq", "together"]:
            available[p] = bool(cfg.get_api_key(p))

        print("LLM Provider Status")
        print("")
        print(f"Default Provider: {default_provider}")
        print(f"Priority Mode: {priority_mode}")
        print("")
        print("Providers:")
        for provider in sorted(priorities.keys(), key=lambda x: int(priorities[x])):
            is_configured = bool(configured.get(provider, False))
            is_available = bool(available.get(provider, False))
            if not is_configured:
                status = "✗ Not configured"
            elif is_available:
                status = "✓ Available"
            else:
                status = "⚠ Configured but unreachable"

            model = cfg.get_model(provider) if hasattr(cfg, "get_model") else ""
            pr = int(priorities.get(provider, 100))
            print(f"  [{pr:2d}] {provider:10s} {status}  Model: {model}")
        print("")
        print("Priority: lower number = tried first")
        return


def main(argv=None):
    cli_start = time.time()
    parser = argparse.ArgumentParser(
        description="Analyze source code and generate logical representations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    epilog = """
Examples:
  code2logic /path/to/project                    # Standard Markdown
  code2logic /path/to/project -f csv             # CSV (best for LLM, ~50% smaller)
  code2logic /path/to/project -f yaml            # YAML (human-readable)
  code2logic /path/to/project -f json --flat     # Flat JSON (for comparisons)
  code2logic /path/to/project -f compact         # Ultra-compact text
  code2logic /path/to/project -f logicml         # LogicML (compressed, reproduction-oriented)
  code2logic /path/to/project -f toon            # TOON (token-oriented tabular format)

Output formats (token efficiency):
  csv      - Best for LLM (~20K tokens/100 files) - flat table
  compact  - Good for LLM (~25K tokens/100 files) - minimal text
  json     - Standard (~35K tokens/100 files) - nested/flat
  yaml     - Readable (~35K tokens/100 files) - nested/flat
  logicml  - Compressed (best compression) - reproduction-oriented
  toon     - Token-oriented (~JSON-size, more LLM-friendly) - tabular arrays
  hybrid   - Optimal balance (70% YAML size, 90% info, best LLM quality)
  gherkin  - Behavioral scenarios - good for minimal implementations
  markdown - Documentation (~55K tokens/100 files)

Detail levels (columns in csv/json/yaml):
  minimal  - path, type, name, signature (4 columns)
  standard - + intent, category, domain, imports (8 columns)
  full     - + calls, lines, complexity, hash (16 columns)
"""
    parser.add_argument(
        "path", nargs="?", default=None, help="Path to the project directory"
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=[
            "markdown",
            "compact",
            "json",
            "yaml",
            "hybrid",
            "csv",
            "gherkin",
            "toon",
            "logicml",
        ],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "-d",
        "--detail",
        choices=["minimal", "standard", "full", "detailed"],
        default="standard",
        help="Detail level - columns to include (default: standard)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        dest="output_dir",
        help="Output directory for all generated files. If specified, files are saved instead of stdout. File names are derived from --name and format flags: {name}.{format}, {name}.functions.{ext}, {name}.{format}-schema.json",
    )
    parser.add_argument(
        "--name",
        dest="project_name",
        help='Project name for output files (default: from CODE2LOGIC_PROJECT_NAME env or "project"). Used for auto-generating output, schema, and function-logic file names.',
    )
    parser.add_argument(
        "--function-logic",
        nargs="?",
        const="auto",
        default=None,
        help="Write detailed function logic to a separate file. If no path given, auto-generates based on output file or uses project.functions.logicml. Format inferred from extension: .logicml/.json/.yaml/.toon",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Use flat structure (for json/yaml) - better for comparisons",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Use compact YAML format (14%% smaller, meta.legend transparency)",
    )
    parser.add_argument(
        "--ultra-compact",
        action="store_true",
        help="Use ultra-compact TOON format (71%% smaller, single-letter keys)",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Use hybrid format (70%% of YAML size, 90%% of info, best LLM quality)",
    )
    parser.add_argument(
        "--with-schema",
        action="store_true",
        help="Generate JSON schema file alongside output (uses project name for filename)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write all output to stdout instead of files (including schema and function-logic). Useful for piping.",
    )
    parser.add_argument(
        "--no-repeat-module",
        action="store_true",
        dest="no_repeat_module",
        help="Reduce repeated directory prefixes in TOON outputs by using ./file for consecutive entries in the same folder (applies to function-logic TOON and TOON module lists).",
    )
    parser.add_argument(
        "--no-repeat-name",
        action="store_true",
        dest="no_repeat_module",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-repeat-details",
        action="store_true",
        help="Reduce repeated directory prefixes in function-logic TOON section function_details by using ./file for consecutive entries in the same folder.",
    )
    parser.add_argument(
        "--does",
        action="store_true",
        help="Include the does/intent column in function-logic TOON output. Without this flag, the does column is omitted to save tokens.",
    )
    parser.add_argument(
        "--function-logic-context",
        choices=["none", "minimal", "full"],
        default="none",
        dest="function_logic_context",
        help="Structural context in function-logic TOON: none (flat list), minimal (class headers with bases), full (classes + properties + imports). Default: none.",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Skip auto-installation of dependencies",
    )
    parser.add_argument(
        "--no-treesitter",
        action="store_true",
        help="Disable Tree-sitter (use fallback parser)",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Do not respect .gitignore (scan all files under path)",
    )
    parser.add_argument(
        "--no-similarity",
        action="store_true",
        help="Disable similarity detection (RapidFuzz) to speed up analysis on large projects",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output with progress info"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Debug output (very verbose)"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress all output except errors"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show library availability status and exit",
    )
    parser.add_argument(
        "--profile-llm",
        action="store_true",
        help="Profile LLM capabilities and save to ~/.code2logic/llm_profiles.json",
    )
    parser.add_argument(
        "--profile-quick",
        action="store_true",
        help="Run quick LLM profile (fewer tests)",
    )
    parser.add_argument(
        "--show-profiles", action="store_true", help="Show saved LLM profiles"
    )

    if len(sys.argv) == 1 or any(a in ("-h", "--help") for a in sys.argv[1:]):
        parser.print_help()
        return

    args = parser.parse_args(argv)

    if not args.no_install and os.environ.get("CODE2LOGIC_NO_INSTALL") in (
        "1",
        "true",
        "True",
        "yes",
        "YES",
    ):
        args.no_install = True

    if (
        not args.verbose
        and not args.quiet
        and os.environ.get("CODE2LOGIC_VERBOSE") in ("1", "true", "True", "yes", "YES")
    ):
        args.verbose = True

    if args.detail == "detailed":
        args.detail = "full"

    # Initialize logger
    log = Logger(verbose=args.verbose, debug=args.debug)

    logging.basicConfig(
        level=(
            logging.DEBUG
            if args.debug
            else (logging.INFO if args.verbose else logging.WARNING)
        ),
        format="[%(levelname)s] %(message)s",
    )

    if args.verbose and not args.quiet:
        log.header("CODE2LOGIC")
        log.detail(f"Version: {__version__}")
        log.detail(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Auto-install dependencies unless disabled
    if not args.no_install and not args.status:
        if args.verbose:
            log.step("Checking dependencies...")
        ensure_dependencies()
        if args.verbose:
            log.detail("Dependencies OK")

    # Import after potential installation
    from .analyzer import ProjectAnalyzer, get_library_status
    from .config import Config
    from .function_logic import FunctionLogicGenerator
    from .generators import (
        CSVGenerator,
        CompactGenerator,
        JSONGenerator,
        MarkdownGenerator,
        YAMLGenerator,
    )
    from .logicml import LogicMLGenerator
    from .toon_format import TOONGenerator

    # Load config to get project name
    config = Config()

    # Status check
    if args.status:
        status = get_library_status()
        print("Library Status:")
        for lib, available in status.items():
            symbol = "✓" if available else "✗"
            print(f"  {lib}: {symbol}")
        sys.exit(0)

    # Show LLM profiles
    if args.show_profiles:
        from .llm_profiler import load_profiles

        profiles = load_profiles()
        if not profiles:
            print("No LLM profiles saved yet.")
            print("Run: code2logic --profile-llm to create one")
        else:
            print(f"Saved LLM Profiles ({len(profiles)}):")
            print("-" * CONSTANT_60)
            for _pid, p in profiles.items():
                print(f"\n{Colors.BOLD}{p.provider}/{p.model}{Colors.NC}")
                print(f"  Profile ID: {p.profile_id}")
                print(f"  Created: {p.created_at}")
                print(f"  Effective context: {p.effective_context} tokens")
                print(f"  Optimal chunk: {p.optimal_chunk_size} tokens")
                print(f"  Syntax accuracy: {p.syntax_accuracy:.0%}")
                print(f"  Semantic accuracy: {p.semantic_accuracy:.0%}")
                print(f"  Preferred format: {p.preferred_format}")
        sys.exit(0)

    # Profile LLM
    if args.profile_llm:
        from .llm_clients import get_client
        from .llm_profiler import LLMProfiler

        log.info("Profiling LLM capabilities...")

        try:
            client = get_client()
            provider = getattr(client, "provider", "unknown")
            model = getattr(client, "model", "unknown")

            log.info(f"Using: {provider}/{model}")

            profiler = LLMProfiler(client, verbose=True)
            profile = profiler.run_profile(quick=args.profile_quick)

            log.success(f"Profile saved: {profile.profile_id}")
            print(f"\nRecommendations for {provider}/{model}:")
            print(f"  Optimal chunk size: {profile.optimal_chunk_size} tokens")
            print(f"  Preferred format: {profile.preferred_format}")
            print(f"  Syntax accuracy: {profile.syntax_accuracy:.0%}")
            print(f"  Semantic accuracy: {profile.semantic_accuracy:.0%}")

        except Exception as e:
            log.error(f"Profiling failed: {e}")
            sys.exit(1)

        sys.exit(0)

    # Path is required for analysis
    if args.path is None:
        parser.print_help()
        return

    # Validate path
    if not os.path.exists(args.path):
        log.error(f"Path does not exist: {args.path}")
        sys.exit(1)

    if not os.path.isdir(args.path):
        log.error(f"Path is not a directory: {args.path}")
        sys.exit(1)

    # Analyze
    if args.verbose:
        log.step(f"Analyzing project: {args.path}")
        log.detail(
            f"Parser: {'Tree-sitter' if not args.no_treesitter else 'Fallback regex'}"
        )

    analyze_start = time.time()
    analyzer = ProjectAnalyzer(
        args.path,
        use_treesitter=not args.no_treesitter,
        verbose=args.verbose or args.debug,
        enable_similarity=not args.no_similarity,
        respect_gitignore=not args.no_gitignore,
    )
    project = analyzer.analyze()
    analyze_time = time.time() - analyze_start

    if args.verbose:
        log.success(f"Analysis complete ({analyze_time:.2f}s)")
        log.separator()
        log.stats("Files", project.total_files)
        log.stats("Lines", f"{project.total_lines:,}")
        log.stats("Languages", ", ".join(project.languages.keys()))
        log.stats("Modules", len(project.modules))

        total_functions = sum(len(m.functions) for m in project.modules)
        total_classes = sum(len(m.classes) for m in project.modules)
        log.stats("Functions", total_functions)
        log.stats("Classes", total_classes)

        if project.entrypoints:
            log.stats("Entrypoints", ", ".join(project.entrypoints[:CONSTANT_3]))

        log.separator()

    # Get project name: CLI arg > env var > default
    project_name = args.project_name if args.project_name else config.get_project_name()

    # Determine output mode:
    # - --stdout: all requested output to stdout (with section markers)
    # - -o ./dir with --function-logic or --with-schema: only generate flagged files
    # - -o ./dir without aux flags: generate main file only
    # - no -o: main to stdout (auxiliary files require explicit path)
    use_stdout = args.stdout
    output_dir = args.output_dir

    # When using output_dir with aux flags, only generate those files (not main)
    has_aux_flags = args.function_logic or args.with_schema
    generate_main = not has_aux_flags or use_stdout

    # Build output paths based on output_dir
    ext_map = {
        "markdown": "md",
        "compact": "txt",
        "json": "json",
        "yaml": "yaml",
        "hybrid": "yaml",
        "csv": "csv",
        "gherkin": "feature",
        "toon": "toon",
        "logicml": "logicml",
    }
    ext = ext_map.get(args.format, args.format)
    main_output_path = None
    if output_dir and generate_main:
        main_output_path = os.path.join(output_dir, f"{project_name}.{ext}")

    # Generate output
    if args.verbose:
        log.step(f"Generating {args.format} output (detail: {args.detail})")

    gen_start = time.time()

    if args.format == "markdown":
        generator = MarkdownGenerator()
        output = generator.generate(project, args.detail)
    elif args.format == "compact":
        generator = CompactGenerator()
        output = generator.generate(project)
    elif args.format == "csv":
        generator = CSVGenerator()
        output = generator.generate(project, detail=args.detail)
    elif args.format == "gherkin":
        from .gherkin import GherkinGenerator

        generator = GherkinGenerator()
        output = generator.generate(project, detail=args.detail)
    elif args.format == "json":
        generator = JSONGenerator()
        output = generator.generate(project, flat=args.flat, detail=args.detail)
    elif args.format in ("yaml", "hybrid"):
        generator = YAMLGenerator()
        compact = args.compact if hasattr(args, "compact") else False
        hybrid = (args.format == "hybrid") or (
            args.hybrid if hasattr(args, "hybrid") else False
        )

        if hybrid:
            output = generator.generate_hybrid(project, detail=args.detail)
        else:
            output = generator.generate(
                project, flat=args.flat, detail=args.detail, compact=compact
            )

        # Generate schema if requested
        if args.with_schema:
            if hybrid:
                schema = generator.generate_schema("hybrid")
            else:
                schema = generator.generate_schema("compact" if compact else "full")

            if use_stdout:
                # Write to stdout with section marker
                print("\n=== SCHEMA ===")
                print(schema)
            elif output_dir:
                # Write to file in output directory
                schema_path = os.path.join(
                    output_dir, f"{project_name}.yaml-schema.json"
                )
                os.makedirs(output_dir, exist_ok=True)
                with open(schema_path, "w", encoding="utf-8") as f:
                    f.write(schema)
                if args.verbose:
                    log.success(f"Schema written to: {schema_path}")

    elif args.format == "toon":
        generator = TOONGenerator()
        # For TOON, --compact means ultra-compact format
        compact = args.compact if hasattr(args, "compact") else False
        ultra_compact = args.ultra_compact if hasattr(args, "ultra_compact") else False
        use_hybrid = args.hybrid if hasattr(args, "hybrid") else False

        # Use compact or ultra_compact flag (compact takes precedence for TOON)
        use_ultra_compact = ultra_compact or compact

        if use_hybrid:
            output = generator.generate_hybrid(
                project,
                detail="full",
                no_repeat_name=args.no_repeat_module,
            )
        elif use_ultra_compact:
            output = generator.generate_ultra_compact(project)
        else:
            detail_map = {
                "minimal": "compact",
                "standard": "standard",
                "full": "full",
            }
            output = generator.generate(
                project,
                detail=detail_map.get(args.detail, "standard"),
                no_repeat_name=args.no_repeat_module,
            )

        # Generate schema if requested
        if args.with_schema:
            schema_type = "ultra_compact" if use_ultra_compact else "standard"
            schema = generator.generate_schema(schema_type)

            if use_stdout:
                # Write to stdout with section marker
                print("\n=== SCHEMA ===")
                print(schema)
            elif output_dir:
                # Write to file in output directory
                schema_path = os.path.join(
                    output_dir, f"{project_name}.toon-schema.json"
                )
                os.makedirs(output_dir, exist_ok=True)
                with open(schema_path, "w", encoding="utf-8") as f:
                    f.write(schema)
                if args.verbose:
                    log.success(f"Schema written to: {schema_path}")

    elif args.format == "logicml":
        generator = LogicMLGenerator()
        spec = generator.generate(project, detail=args.detail)
        output = spec.content
    else:
        log.error(f"Unsupported format: {args.format}")
        sys.exit(1)

    # Optional: write detailed function logic to a separate file
    if args.function_logic:
        logic_gen = FunctionLogicGenerator()

        # Determine path for function logic file
        if args.function_logic == "auto":
            if output_dir:
                # Use output directory with project name
                logic_ext = ext_map.get(args.format, "logicml")
                logic_path = os.path.join(
                    output_dir, f"{project_name}.functions.{logic_ext}"
                )
            else:
                # No output dir - use project name in current directory
                logic_ext = ext_map.get(args.format, "logicml")
                logic_path = f"{project_name}.functions.{logic_ext}"
        else:
            logic_path = str(args.function_logic)

        lower = logic_path.lower()
        if lower.endswith(".json"):
            logic_out = logic_gen.generate_json(project, detail=args.detail)
        elif lower.endswith((".yaml", ".yml")):
            logic_out = logic_gen.generate_yaml(project, detail=args.detail)
        elif lower.endswith(".toon"):
            logic_out = logic_gen.generate_toon(
                project,
                detail=args.detail,
                no_repeat_name=args.no_repeat_module,
                no_repeat_details=args.no_repeat_details,
                include_does=args.does,
                context=getattr(args, "function_logic_context", "none") or "none",
            )
        else:
            logic_out = logic_gen.generate(project, detail=args.detail)

        # Generate function-logic schema if requested and format is TOON
        func_schema = None
        if args.with_schema and lower.endswith(".toon"):
            func_schema = logic_gen.generate_toon_schema()

        if use_stdout:
            # Write to stdout with section marker
            print("\n=== FUNCTION_LOGIC ===")
            print(logic_out)
            if func_schema:
                print("\n=== FUNCTION_LOGIC_SCHEMA ===")
                print(func_schema)
        elif output_dir:
            # Write to file in output directory
            os.makedirs(output_dir, exist_ok=True)
            with open(logic_path, "w", encoding="utf-8") as f:
                f.write(logic_out)
            if args.verbose:
                log.success(f"Function logic written to: {logic_path}")
            if func_schema:
                schema_path = logic_path.replace(".toon", "-schema.json")
                with open(schema_path, "w", encoding="utf-8") as f:
                    f.write(func_schema)
                if args.verbose:
                    log.success(f"Function logic schema written to: {schema_path}")

    gen_time = time.time() - gen_start

    if args.verbose:
        output_size = len(output)
        tokens_approx = output_size // CONSTANT_4
        log.success(f"Output generated ({gen_time:.2f}s)")
        log.stats("Size", f"{output_size:,} chars (~{tokens_approx:,} tokens)")
        log.stats("Lines", output.count("\n") + 1)

    # Write main output (only if generate_main is True)
    if generate_main:
        if output_dir:
            # Write to file in output directory
            os.makedirs(output_dir, exist_ok=True)
            with open(main_output_path, "w", encoding="utf-8") as f:
                f.write(output)
            if args.verbose:
                log.success(f"Output written to: {main_output_path}")
        else:
            # Write to stdout
            if not args.quiet:
                try:
                    print(output, flush=True)
                except BrokenPipeError:
                    try:
                        sys.stdout.close()
                    except Exception:
                        pass
                    os._exit(0)

    # Final summary
    if args.verbose:
        total_time = time.time() - cli_start
        log.separator()
        log.info(f"Total time: {total_time:.2f}s")


if __name__ == "__main__":
    main()
