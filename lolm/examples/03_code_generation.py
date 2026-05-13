#!/usr/bin/env python3
"""
LOLM Code Generation Example

Using lolm for code generation tasks.
"""

from lolm import get_client

SYSTEM_PROMPT = """You are an expert Python programmer. 
Generate clean, well-documented code following PEP 8 guidelines.
Include type hints and docstrings."""


def generate_function(description: str) -> str:
    """Generate a Python function from description."""
    client = get_client()

    prompt = f"""Generate a Python function that:
{description}

Requirements:
- Include type hints
- Include docstring with Args and Returns
- Handle edge cases
- Be efficient

Return only the code, no explanations."""

    return client.generate(prompt, system=SYSTEM_PROMPT, max_tokens=1000)


def generate_class(description: str) -> str:
    """Generate a Python class from description."""
    client = get_client()

    prompt = f"""Generate a Python class that:
{description}

Requirements:
- Use dataclass if appropriate
- Include type hints
- Include docstrings
- Implement __str__ and __repr__

Return only the code, no explanations."""

    return client.generate(prompt, system=SYSTEM_PROMPT, max_tokens=2000)


def explain_code(code: str) -> str:
    """Explain what a piece of code does."""
    client = get_client()

    prompt = f"""Explain what this code does:

```python
{code}
```

Provide:
1. Brief summary (1-2 sentences)
2. Key functionality
3. Any potential issues"""

    return client.generate(prompt, system="You are a code reviewer.", max_tokens=500)


def review_code(code: str) -> str:
    """Review code for improvements."""
    client = get_client()

    prompt = f"""Review this Python code:

```python
{code}
```

Provide:
1. Code quality score (1-10)
2. Strengths
3. Suggested improvements
4. Refactored version if needed"""

    return client.generate(
        prompt, system="You are a senior Python developer doing code review.", max_tokens=1000
    )


if __name__ == "__main__":
    print("LOLM Code Generation Examples\n")

    # Example 1: Generate a function
    print("=== Generate Function ===")
    func_code = generate_function("calculates the nth Fibonacci number using memoization")
    print(func_code)

    # Example 2: Explain code
    print("\n=== Explain Code ===")
    sample_code = """
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)
"""
    explanation = explain_code(sample_code)
    print(explanation)

    # Example 3: Generate a class
    print("\n=== Generate Class ===")
    class_code = generate_class(
        "represents a Task with title, description, due_date, priority, and status"
    )
    print(class_code)
