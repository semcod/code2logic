"""Setup configuration for code2flow."""

from setuptools import setup, find_packages
import os

# Read version
version = "0.2.1"


# Read long description
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    return "Python code flow analysis tool"


setup(
    name="code2flow",
    version=version,
    description="Python code flow analysis tool - CFG, DFG, and call graph extraction",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="STTS Project",
    author_email="",
    url="https://github.com/wronai/stts",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "code2flow=code2flow.cli:main",
        ],
    },
    install_requires=[
        "networkx>=2.6",
        "matplotlib>=3.4",
        "pyyaml>=5.4",
        "numpy>=1.20",
    ],
    extras_require={
        "dev": [
            "pytest>=6.2",
            "pytest-cov>=2.12",
            "black>=21.0",
            "flake8>=3.9",
            "mypy>=0.910",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Code Generators",
    ],
    keywords="static-analysis control-flow data-flow call-graph reverse-engineering",
    project_urls={
        "Source": "https://github.com/wronai/stts",
        "Tracker": "https://github.com/wronai/stts/issues",
    },
)
