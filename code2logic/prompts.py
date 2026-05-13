"""
Prompt templates for code reproduction.

Optimized prompts for different specification formats.
Based on benchmark results:
- YAML: 70.3% score
- LogicML: 63.6% score, best compression
- Gherkin: 44.1% score (not recommended)
"""

from typing import Dict

# Format-specific hints for LLM prompts
FORMAT_HINTS: Dict[str, str] = {
    "yaml": """Parse the YAML structure precisely:
- 'modules' contains file definitions
- 'classes' with 'methods' and 'attrs'
- 'functions' with 'signature' and 'intent'
Implement all classes and functions with exact signatures.""",
    "logicml": """Generate VALID, RUNNABLE Python code from LogicML spec.

SYNTAX RULES:
- 'sig: (params) -> Type' = def method(params) -> Type:
- 'sig: async (params)' = async def method(params):
- 'sig: @property (self)' = @property decorator above method
- 'bases: [BaseModel]' = Pydantic: class X(BaseModel): with Field()
- 'attrs:' = self.attr = value in __init__
- 'type: re-export' = from .submodule import Name

CRITICAL REQUIREMENTS:
1. ALL brackets/parentheses MUST be balanced
2. ALL imports MUST be at file top
3. NO undefined variables
4. Proper 4-space indentation
5. Each class/function MUST be complete""",
    "gherkin": """Implement scenarios as SIMPLE, MINIMAL Python code:
- NO extra error classes or exception hierarchies
- NO over-engineering or unnecessary abstractions
- Keep code short and direct
- Focus on core functionality only.""",
    "markdown": """Parse the embedded sections:
- YAML blocks contain structure (imports, classes, functions)
- Gherkin blocks describe behaviors
Implement all structures with proper type hints.""",
    "json": """Parse the JSON structure:
- 'modules' array with 'path', 'classes', 'functions'
- 'classes' have 'name', 'methods', 'properties'
- 'functions' have 'name', 'params', 'returns'
Implement all elements with proper types.""",
}


def get_reproduction_prompt(
    spec: str,
    fmt: str,
    file_name: str,
    language: str = "python",
    max_spec_length: int = 5000,
) -> str:
    """Generate optimized reproduction prompt.

    Args:
        spec: Specification content
        fmt: Format name (yaml, logicml, gherkin, etc.)
        file_name: Target file name
        language: Target programming language
        max_spec_length: Maximum spec length to include

    Returns:
        Formatted prompt string
    """
    hint = FORMAT_HINTS.get(fmt, "")
    spec_truncated = spec[:max_spec_length] if len(spec) > max_spec_length else spec

    return f"""Generate {language} code from this {fmt.upper()} specification.
{hint}

{spec_truncated}

Requirements:
- Complete, working {language} code for {file_name}
- Include all necessary imports
- Add type hints to all functions
- Implement all functions with actual logic (no pass or NotImplementedError)

```{language}
"""


def get_review_prompt(code: str, spec: str, fmt: str) -> str:
    """Generate code review prompt.

    Args:
        code: Generated code to review
        spec: Original specification
        fmt: Format name

    Returns:
        Review prompt string
    """
    return f"""Review this generated code against the {fmt.upper()} specification.

SPECIFICATION:
{spec[:2000]}

GENERATED CODE:
{code[:3000]}

Check for:
1. Missing functions or classes
2. Incorrect signatures
3. Missing type hints
4. Logic errors
5. Missing edge case handling

Provide a JSON response:
{{
    "score": 0-100,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1"]
}}
"""


def get_fix_prompt(code: str, issues: list, spec: str) -> str:
    """Generate code fix prompt.

    Args:
        code: Code with issues
        issues: List of identified issues
        spec: Original specification

    Returns:
        Fix prompt string
    """
    issues_text = "\n".join(f"- {issue}" for issue in issues)

    return f"""Fix the following issues in this code:

ISSUES:
{issues_text}

ORIGINAL SPEC:
{spec[:1500]}

CURRENT CODE:
{code[:3000]}

Generate the corrected complete code:

```python
"""
