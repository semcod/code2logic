"""
Entry point for running logic2test as a module.

Usage:
    python -m logic2test project.c2l.yaml -o tests/
"""

from .cli import main

if __name__ == "__main__":
    main()
