"""
Code reproduction utilities.

Functions for:
- Generating Gherkin from single files
- Comparing original vs generated code
- Code quality analysis

Usage:
    from code2logic.reproduction import (
        generate_file_gherkin,
        compare_code,
        CodeReproducer
    )
"""

import difflib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .llm_clients import BaseLLMClient, get_client


def generate_file_gherkin(file_path: Path) -> str:
    """Generate detailed Gherkin specification for a single file with types.

    Args:
        file_path: Path to the source file

    Returns:
        Gherkin specification string
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    content = file_path.read_text()

    # Extract structure from file
    classes = []
    functions = []
    imports = []
    module_doc = ""

    lines = content.split("\n")
    in_class = None
    in_docstring = False
    in_class_docstring = False
    docstring_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Module docstring (first few lines)
        if i < 5 and stripped.startswith('"""') and not module_doc:
            if stripped.count('"""') >= 2:
                module_doc = stripped.strip('"""').strip()
            else:
                in_docstring = True
                docstring_lines = [stripped.lstrip('"""')]
                continue

        if in_docstring and not in_class:
            if '"""' in stripped:
                docstring_lines.append(stripped.rstrip('"""'))
                module_doc = " ".join(docstring_lines)[:200]
                in_docstring = False
            else:
                docstring_lines.append(stripped)
            continue

        # Class docstring
        if in_class_docstring:
            if '"""' in stripped:
                docstring_lines.append(stripped.rstrip('"""'))
                class_docstring = " ".join(docstring_lines)[:150]
                classes[-1]["docstring"] = class_docstring
                in_class_docstring = False
            else:
                docstring_lines.append(stripped)
            continue

        # Imports
        if stripped.startswith("from ") or stripped.startswith("import "):
            imports.append(stripped)

        # Classes
        if stripped.startswith("class "):
            class_name = stripped.split("(")[0].split(":")[0].replace("class ", "")
            in_class = class_name
            classes.append(
                {"name": class_name, "attributes": [], "methods": [], "docstring": ""}
            )

        # Class docstring start
        if in_class and stripped.startswith('"""') and not classes[-1]["docstring"]:
            if stripped.count('"""') >= 2:
                classes[-1]["docstring"] = stripped.strip('"""').strip()[:100]
            else:
                in_class_docstring = True
                docstring_lines = [stripped.lstrip('"""')]
            continue

        # Class attributes with FULL type info
        if (
            in_class
            and ":" in stripped
            and not stripped.startswith("def ")
            and not stripped.startswith("#")
        ):
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if any(
                stripped.startswith(x)
                for x in [
                    "Attributes",
                    "-",
                    "Args",
                    "Returns",
                    "Raises",
                    "Note",
                    "Example",
                ]
            ):
                continue
            if any(
                x in stripped.lower()
                for x in [
                    "path to",
                    "the ",
                    "a ",
                    "an ",
                    "this ",
                    "that ",
                    "if ",
                    "when ",
                ]
            ):
                continue
            if stripped[0].islower() and not re.match(
                r"^[a-z_][a-z0-9_]*\s*:", stripped
            ):
                continue

            attr_full = stripped
            if attr_full and not attr_full.startswith("return"):
                attr_name = attr_full.split(":")[0].strip()
                if (
                    attr_name
                    and attr_name.isidentifier()
                    and attr_name
                    not in ["try", "if", "for", "while", "class", "def", "return"]
                ):
                    existing = [
                        a["name"]
                        for a in classes[-1]["attributes"]
                        if isinstance(a, dict)
                    ]
                    if attr_name not in existing:
                        classes[-1]["attributes"].append(
                            {"name": attr_name, "full": attr_full}
                        )

        # Functions/methods with signatures
        if stripped.startswith("def "):
            func_line = stripped
            if func_line.endswith(":"):
                func_line = func_line[:-1]
            func_name = func_line.split("(")[0].replace("def ", "")

            try:
                params_part = func_line.split("(", 1)[1].rsplit(")", 1)[0]
                return_part = (
                    func_line.split("->")[-1].strip() if "->" in func_line else "None"
                )
            except (IndexError, ValueError):
                params_part = ""
                return_part = "None"

            func_info = {
                "name": func_name,
                "params": params_part,
                "returns": return_part,
                "full": func_line,
            }

            if in_class:
                classes[-1]["methods"].append(func_info)
            else:
                functions.append(func_info)

    # Generate detailed Gherkin
    gherkin_lines = [
        f"# Gherkin specification for {file_path.name}",
        f"# {module_doc}" if module_doc else "# Python module",
        "",
        f"@{file_path.stem}",
        f"Feature: {file_path.stem} module",
        f"  {module_doc[:100]}" if module_doc else f"  Source file: {file_path.name}",
        "",
    ]

    if imports:
        gherkin_lines.append("  Background:")
        gherkin_lines.append("    Given the following imports are required:")
        for imp in imports[:10]:
            gherkin_lines.append(f"      | {imp} |")
        gherkin_lines.append("")

    is_dataclass = "@dataclass" in content

    for cls in classes:
        gherkin_lines.append("  @dataclass" if is_dataclass else "  @class")
        gherkin_lines.append(
            f"  Scenario: Define {cls['name']} {'dataclass' if is_dataclass else 'class'}"
        )

        if cls["docstring"]:
            gherkin_lines.append(f"    # {cls['docstring'][:80]}")

        gherkin_lines.append(
            f'    Given a {"dataclass" if is_dataclass else "class"} named "{cls["name"]}"'
        )

        if cls["attributes"]:
            gherkin_lines.append(
                "    Then it should have the following typed attributes:"
            )
            gherkin_lines.append("      | name | type | default |")
            for attr in cls["attributes"]:
                if isinstance(attr, dict):
                    full = attr["full"]
                    name = attr["name"]
                    type_part = ""
                    default_part = ""
                    if ":" in full:
                        after_colon = full.split(":", 1)[1].strip()
                        if "=" in after_colon:
                            type_part = after_colon.split("=")[0].strip()
                            default_part = after_colon.split("=", 1)[1].strip()
                        else:
                            type_part = after_colon
                    gherkin_lines.append(
                        f"      | {name} | {type_part} | {default_part} |"
                    )
                else:
                    gherkin_lines.append(f"      | {attr} | | |")

        if cls["methods"]:
            gherkin_lines.append("    And it should have the following methods:")
            gherkin_lines.append("      | name | params | returns |")
            for method in cls["methods"]:
                if isinstance(method, dict):
                    gherkin_lines.append(
                        f"      | {method['name']} | {method['params'][:50]} | {method['returns']} |"
                    )
                else:
                    gherkin_lines.append(f"      | {method} | | |")

        gherkin_lines.append("")

    for func in functions:
        if isinstance(func, dict):
            gherkin_lines.append(f"  Scenario: Define {func['name']} function")
            gherkin_lines.append(f'    Given a function named "{func["name"]}"')
            gherkin_lines.append(f"    With parameters: {func['params']}")
            gherkin_lines.append(f"    And returns: {func['returns']}")
        else:
            gherkin_lines.append(f"  Scenario: Define {func} function")
            gherkin_lines.append(f'    Given a function named "{func}"')
        gherkin_lines.append("")

    return "\n".join(gherkin_lines)


def compare_code(original: str, generated: str) -> Dict[str, Any]:
    """Compare original and generated code.

    Args:
        original: Original source code
        generated: Generated code

    Returns:
        Dictionary with comparison metrics
    """

    def normalize(code: str) -> List[str]:
        lines = code.strip().split("\n")
        return [line.rstrip() for line in lines if line.strip()]

    orig_lines = normalize(original)
    gen_lines = normalize(generated)

    matcher = difflib.SequenceMatcher(None, orig_lines, gen_lines)
    similarity = matcher.ratio() * 100

    diff = list(
        difflib.unified_diff(
            orig_lines, gen_lines, fromfile="original", tofile="generated", lineterm=""
        )
    )

    def count_elements(code: str) -> Dict[str, int]:
        return {
            "classes": code.count("class "),
            "functions": code.count("def "),
            "imports": code.count("import "),
            "docstrings": code.count('"""'),
            "lines": len(code.strip().split("\n")),
            "chars": len(code),
        }

    orig_elements = count_elements(original)
    gen_elements = count_elements(generated)

    struct_matches = sum(
        1 for k in orig_elements if orig_elements[k] == gen_elements.get(k, 0)
    )
    struct_score = (struct_matches / len(orig_elements)) * 100

    return {
        "similarity_percent": round(similarity, 2),
        "structural_score": round(struct_score, 2),
        "original_elements": orig_elements,
        "generated_elements": gen_elements,
        "diff_lines": len([d for d in diff if d.startswith("+") or d.startswith("-")]),
        "diff": "\n".join(diff[:50]),
    }


def extract_code_block(text: str, language: str = "python") -> str:
    """Extract code block from LLM response.

    Args:
        text: LLM response text
        language: Expected language

    Returns:
        Extracted code
    """
    s = (text or "").strip()
    if not s:
        return ""

    markers = [f"```{language}", "```py", "```"]
    for marker in markers:
        idx = s.find(marker)
        if idx == -1:
            continue

        start = idx + len(marker)
        if start < len(s) and s[start] == "\n":
            start += 1

        end = s.find("```", start)
        if end == -1:
            return s[start:].strip()
        if end > start:
            return s[start:end].strip()

    return s


class CodeReproducer:
    """Code reproduction workflow using LLM."""

    def __init__(self, client: BaseLLMClient = None, provider: str = None):
        """Initialize reproducer.

        Args:
            client: LLM client to use
            provider: Provider name if client not provided
        """
        self.client = client or get_client(provider)

    def reproduce_file(
        self, source_path: str, output_dir: str = None
    ) -> Dict[str, Any]:
        """Reproduce code from a source file.

        Args:
            source_path: Path to source file
            output_dir: Optional output directory for results

        Returns:
            Dictionary with reproduction results
        """
        path = Path(source_path)

        # Read original
        original_code = path.read_text()

        # Generate Gherkin
        gherkin = generate_file_gherkin(path)

        # Generate code from Gherkin
        generated_code = self.generate_from_gherkin(gherkin)

        # Compare
        comparison = compare_code(original_code, generated_code)

        results = {
            "timestamp": datetime.now().isoformat(),
            "source_file": str(source_path),
            "original_code": original_code,
            "gherkin": gherkin,
            "generated_code": generated_code,
            "comparison": comparison,
        }

        # Save if output_dir provided
        if output_dir:
            self._save_results(Path(output_dir), results)

        return results

    def generate_from_gherkin(self, gherkin: str, language: str = "python") -> str:
        """Generate code from Gherkin specification.

        Args:
            gherkin: Gherkin specification
            language: Target language

        Returns:
            Generated code
        """
        system_prompt = f"""You are an expert {language} developer. Generate clean,
production-ready {language} code based on the Gherkin/BDD specification.

Rules:
1. Generate ONLY code, no explanations
2. Include all necessary imports
3. Add docstrings to all functions and classes
4. Follow PEP 8 style guidelines
5. Include type hints
6. The code must be complete and runnable

Output format: Return ONLY the code wrapped in ```{language} ... ``` blocks."""

        prompt = f"""Generate {language} code that implements this Gherkin specification:

{gherkin}

Generate complete, working {language} code with all classes, functions, and methods described.
Include proper docstrings and type hints."""

        response = self.client.generate(prompt, system=system_prompt, max_tokens=8000)
        return extract_code_block(response, language)

    def _save_results(self, output_dir: Path, results: Dict[str, Any]):
        """Save reproduction results to files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "original.py").write_text(results["original_code"])
        (output_dir / "specification.feature").write_text(results["gherkin"])
        (output_dir / "generated.py").write_text(results["generated_code"])

        # Generate report
        report = self._generate_report(results)
        (output_dir / "COMPARISON_REPORT.md").write_text(report)

    def _generate_report(self, results: Dict[str, Any]) -> str:
        """Generate markdown comparison report."""
        comp = results["comparison"]

        return f"""# Code Reproduction Comparison Report

> Generated: {results["timestamp"]}
> Source: `{results["source_file"]}`

## Summary

| Metric | Value |
|--------|-------|
| **Similarity** | {comp["similarity_percent"]}% |
| **Structural Score** | {comp["structural_score"]}% |
| **Diff Lines** | {comp["diff_lines"]} |

## Structural Comparison

| Element | Original | Generated | Match |
|---------|----------|-----------|-------|
| classes | {comp["original_elements"]["classes"]} | {comp["generated_elements"]["classes"]} | {"✓" if comp["original_elements"]["classes"] == comp["generated_elements"]["classes"] else "✗"} |
| functions | {comp["original_elements"]["functions"]} | {comp["generated_elements"]["functions"]} | {"✓" if comp["original_elements"]["functions"] == comp["generated_elements"]["functions"] else "✗"} |
| lines | {comp["original_elements"]["lines"]} | {comp["generated_elements"]["lines"]} | {"✓" if comp["original_elements"]["lines"] == comp["generated_elements"]["lines"] else "✗"} |

## Diff (first 50 lines)

```diff
{comp["diff"]}
```
"""
