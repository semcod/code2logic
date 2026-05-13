"""
Entry point for running logic2code as a module.

Usage:
    python -m logic2code project.c2l.yaml -o generated_src/
"""

from .cli import main

if __name__ == "__main__":
    main()
