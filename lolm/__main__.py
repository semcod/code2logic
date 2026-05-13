"""
Entry point for running lolm as a module.

Usage:
    python -m lolm status
    python -m lolm set-provider openrouter
    python -m lolm test
"""

from .cli import main

if __name__ == "__main__":
    main()
