"""
Allow running code2logic as a module: python -m code2logic

Usage:
    python -m code2logic /path/to/project
    python -m code2logic /path/to/project -f gherkin -o tests.feature
"""

try:
    from .cli import main
except ImportError:
    from code2logic.cli import main

if __name__ == "__main__":
    main()
