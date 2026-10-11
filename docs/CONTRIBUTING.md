# Contributing to Advanced Data Analysis & Refactoring Pipeline

## Overview

Thank you for your interest in contributing to the Advanced Data Analysis & Refactoring Pipeline! This document provides guidelines and information for contributors.

## 🤝 How to Contribute

### Reporting Issues

1. **Search Existing Issues**: Check if the issue has already been reported
2. **Create New Issue**: Use the issue templates provided
3. **Provide Detailed Information**: Include:
   - Python version and platform
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages and logs
   - Sample code if applicable

### Submitting Pull Requests

1. **Fork the Repository**: Create a personal fork
2. **Create Feature Branch**: Use descriptive branch names
3. **Make Changes**: Follow coding standards and guidelines
4. **Add Tests**: Include unit tests for new functionality
5. **Update Documentation**: Update relevant documentation
6. **Submit PR**: Use pull request template

## 🛠️ Development Setup

### Prerequisites

- Python 3.8+ (recommended 3.9+)
- Git
- GitHub account

### Setup Steps

```bash
# 1. Fork and clone the repository
git clone https://github.com/your-username/nlp2cmd.git
cd nlp2cmd/debug

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install development dependencies
pip install -r requirements-dev.txt

# 4. Install pre-commit hooks
pre-commit install

# 5. Run tests to verify setup
python -m pytest tests/
```

### Development Dependencies

```txt
# requirements-dev.txt
networkx>=2.8
pyyaml>=6.0
matplotlib>=3.5
plotly>=5.0
pytest>=7.0
pytest-cov>=4.0
black>=22.0
flake8>=5.0
mypy>=0.991
pre-commit>=2.20
jupyter>=1.0
sphinx>=5.0
sphinx-rtd-theme>=1.0
```

## 📝 Coding Standards

### Code Style

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some additional guidelines:

```python
# Good example
class DataAnalyzer:
    """Analyze data structures and patterns."""
    
    def __init__(self, config: AnalysisConfig) -> None:
        """Initialize analyzer with configuration."""
        self.config = config
        self._results: List[AnalysisResult] = []
    
    def analyze(self, data: Dict[str, Any]) -> AnalysisResult:
        """Analyze the provided data.
        
        Args:
            data: Dictionary containing data to analyze
            
        Returns:
            AnalysisResult with insights and recommendations
            
        Raises:
            AnalysisError: If analysis fails
        """
        try:
            # Implementation here
            return AnalysisResult(
                function="analyze",
                insights_count=len(data),
                status="completed"
            )
        except Exception as e:
            raise AnalysisError(f"Analysis failed: {e}") from e
```

### Type Hints

Use type hints for all public functions and methods:

```python
from typing import Dict, List, Optional, Union, Any
from pathlib import Path

def process_data(
    input_path: Path,
    output_path: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process data from input path."""
    pass
```

### Documentation

Use comprehensive docstrings following Google style:

```python
def calculate_centrality_metrics(
    graph: nx.Graph,
    metrics: List[str] = ["betweenness", "closeness"]
) -> Dict[str, Dict[str, float]]:
    """Calculate centrality metrics for graph nodes.
    
    This function calculates various centrality metrics for each node
    in the provided graph, which can be used to identify important
    nodes in the network structure.
    
    Args:
        graph: NetworkX graph object
        metrics: List of centrality metrics to calculate
        
    Returns:
        Dictionary mapping metric names to node centrality values
        
    Raises:
        ValueError: If graph is empty or invalid metrics provided
        
    Example:
        >>> G = nx.path_graph(5)
        >>> result = calculate_centrality_metrics(G)
        >>> print(result["betweenness"])
        {'0': 0.0, '1': 0.5, '2': 0.667, '3': 0.5, '4': 0.0}
    """
    pass
```

## 🧪 Testing

### Test Structure

```
tests/
├── unit/
│   ├── test_analyzer.py
│   ├── test_visualization.py
│   └── test_refactoring.py
├── integration/
│   ├── test_pipeline.py
│   └── test_end_to_end.py
├── fixtures/
│   ├── sample_data.yaml
│   └── test_graphs.py
└── conftest.py
```

### Writing Tests

```python
import pytest
from ultimate_advanced_data_analyzer import UltimateAdvancedDataAnalyzer
from pathlib import Path

class TestDataAnalyzer:
    """Test cases for UltimateAdvancedDataAnalyzer."""
    
    @pytest.fixture
    def sample_data(self):
        """Fixture providing sample data for testing."""
        return {
            "nodes": {"node1": {"type": "function"}, "node2": {"type": "class"}},
            "edges": [("node1", "node2")]
        }
    
    def test_analyze_data_hubs(self, sample_data, tmp_path):
        """Test data hubs analysis."""
        # Setup
        analyzer = UltimateAdvancedDataAnalyzer(str(tmp_path))
        
        # Execute
        result = analyzer.analyze_data_hubs_and_consolidation()
        
        # Assert
        assert result["function"] == "analyze_data_hubs_and_consolidation"
        assert "insights_count" in result
        assert "llm_query" in result
        assert result["status"] == "completed"
    
    def test_invalid_path(self):
        """Test handling of invalid paths."""
        with pytest.raises(FileNotFoundError):
            UltimateAdvancedDataAnalyzer("nonexistent_path")
    
    @pytest.mark.parametrize("complexity_threshold", [5, 10, 15])
    def test_different_thresholds(self, sample_data, complexity_threshold, tmp_path):
        """Test analysis with different complexity thresholds."""
        config = AnalysisConfig(complexity_threshold=complexity_threshold)
        analyzer = UltimateAdvancedDataAnalyzer(str(tmp_path))
        analyzer.config = config
        
        result = analyzer.analyze_data_hubs_and_consolidation()
        
        assert result["insights_count"] >= 0
```

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=debug --cov-report=html

# Run specific test file
python -m pytest tests/unit/test_analyzer.py

# Run with verbose output
python -m pytest -v

# Run only failed tests
python -m pytest --lf
```

### Test Coverage

Maintain test coverage above 80%:

```bash
# Check coverage
python -m pytest --cov=debug --cov-fail-under=80

# Generate coverage report
python -m pytest --cov=debug --cov-report=html
open htmlcov/index.html
```

## 📋 Pull Request Process

### Before Submitting

1. **Run Tests**: Ensure all tests pass
2. **Code Style**: Run black and flake8
3. **Type Checking**: Run mypy
4. **Documentation**: Update relevant docs
5. **Changelog**: Add entry to CHANGELOG.md

### Quality Checks

```bash
# Format code
black debug/

# Check style
flake8 debug/

# Type checking
mypy debug/

# Run tests
python -m pytest

# Check coverage
python -m pytest --cov=debug --cov-fail-under=80
```

### Pull Request Template

```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] All tests pass
- [ ] New tests added
- [ ] Coverage maintained

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] No breaking changes (or documented)
```

## 🐛 Bug Reports

### Bug Report Template

```markdown
## Bug Description
Clear and concise description of the bug.

## Steps to Reproduce
1. Step 1
2. Step 2
3. Step 3

## Expected Behavior
What should happen.

## Actual Behavior
What actually happens.

## Environment
- Python version:
- OS:
- Package version:

## Additional Context
Any other relevant information.
```

## 💡 Feature Requests

### Feature Request Template

```markdown
## Feature Description
Clear description of the feature.

## Problem Statement
What problem does this solve?

## Proposed Solution
How should this be implemented?

## Alternatives
What other approaches have you considered?

## Additional Context
Any other relevant information.
```

## 📚 Documentation

### Documentation Types

1. **API Documentation**: Docstrings and type hints
2. **User Guides**: Step-by-step tutorials
3. **Developer Docs**: Architecture and design
4. **Examples**: Code examples and use cases

### Writing Documentation

```markdown
# Feature Title

Brief description of the feature.

## Usage
```python
# Example code
```

## Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| param1 | str | Description of param1 |
| param2 | int | Description of param2 |

## Returns
Description of return value.

## Examples
```python
# Usage example
result = function_name(param1="value", param2=42)
print(result)
```

## Notes
Additional information about the feature.
```

## 🏗️ Architecture

### Project Structure

```
debug/
├── analysis/           # Core analysis functionality
├── visualization/       # Visualization tools
├── refactoring/        # Refactoring implementation
├── utils/             # Utility functions
├── tests/             # Test suite
├── docs/              # Documentation
├── config/            # Configuration files
└── examples/          # Usage examples
```

### Design Principles

1. **Modularity**: Separate concerns into distinct modules
2. **Testability**: Design for easy testing
3. **Extensibility**: Allow for easy extension and customization
4. **Performance**: Optimize for large codebases
5. **Usability**: Provide clear APIs and documentation

### Adding New Features

1. **Design**: Create design document
2. **Implement**: Write code following standards
3. **Test**: Add comprehensive tests
4. **Document**: Update documentation
5. **Review**: Get code review before merging

## 🔧 Development Tools

### IDE Configuration

#### VS Code
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true
}
```

#### PyCharm
- Enable type checking
- Configure code style to PEP 8
- Set up test runner

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 22.3.0
    hooks:
      - id: black
        language_version: python3.9
  
  - repo: https://github.com/pycqa/flake8
    rev: 4.0.1
    hooks:
      - id: flake8
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v0.991
    hooks:
      - id: mypy
        additional_dependencies: [types-PyYAML, types-requests]
```

## 🚀 Release Process

### Version Management

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

1. **Update Version**: Update version in all relevant files
2. **Update Changelog**: Add changes to CHANGELOG.md
3. **Tag Release**: Create git tag
4. **Build Package**: Build distribution packages
5. **Test Release**: Test release candidate
6. **Publish**: Publish to PyPI (if applicable)
7. **Update Docs**: Update online documentation

### Release Commands

```bash
# Update version
bump2version patch  # or minor, major

# Build package
python -m build

# Upload to PyPI (test)
twine upload --repository testpypi dist/*

# Upload to PyPI (production)
twine upload dist/*
```

## 🤝 Community Guidelines

### Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please:

- Be respectful and considerate
- Use inclusive language
- Focus on constructive feedback
- Help others learn and grow

### Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For general questions and ideas
- **Documentation**: For usage and API reference
- **Examples**: For practical implementation guidance

### Communication Channels

- **GitHub**: Primary communication channel
- **Email**: For security issues and private matters
- **Discord/Slack**: For real-time discussion (if available)

## 📖 Resources

### Learning Resources

- [NetworkX Documentation](https://networkx.org/)
- [Plotly Documentation](https://plotly.com/python/)
- [PyYAML Documentation](https://pyyaml.org/)
- [Python Testing](https://docs.pytest.org/)

### Related Projects

- [Code2Flow](https://github.com/scottrogowski/code2flow)
- [NetworkX](https://networkx.org/)
- [Plotly](https://plotly.com/)

### Books and Papers

- "Network Analysis with Python" by Dmitry Zinoviev
- "Graph Algorithms" by Shimon Even
- "Design Patterns" by Gang of Four

---

## 🙏 Acknowledgments

Thank you to all contributors who have helped make this project better!

### Core Contributors
- [@username] - Project lead and architecture
- [@username] - Analysis algorithms
- [@username] - Visualization tools
- [@username] - Documentation and examples

### Special Thanks
- NetworkX team for excellent graph library
- Plotly team for interactive visualization
- Code2Flow for static analysis foundation

---

**Happy contributing!** 🎉

If you have any questions, feel free to open an issue or start a discussion.
