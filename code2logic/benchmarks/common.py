from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..generators import CSVGenerator, JSONGenerator, YAMLGenerator
from ..function_logic import FunctionLogicGenerator
from ..gherkin import GherkinGenerator
from ..logicml import LogicMLGenerator
from ..markdown_format import MarkdownHybridGenerator
from ..models import ProjectInfo
from ..toon_format import TOONGenerator


def create_single_project(module_info, file_path: Path) -> ProjectInfo:
    return ProjectInfo(
        name=file_path.name,
        root_path=str(file_path.parent),
        languages={getattr(module_info, "language", "python") or "python": 1},
        modules=[module_info],
        dependency_graph={},
        dependency_metrics={},
        entrypoints=[],
        similar_functions={},
        total_files=1,
        total_lines=module_info.lines_total,
        generated_at=datetime.now().isoformat(),
    )


def generate_spec(project: ProjectInfo, fmt: str) -> str:
    if fmt == "gherkin":
        gen = GherkinGenerator()
        return gen.generate(project)
    if fmt == "function.toon":
        gen = FunctionLogicGenerator()
        return gen.generate_toon(
            project,
            detail="full",
            no_repeat_name=True,
            no_repeat_details=True,
            include_does=True,
            context="minimal",
        )
    if fmt == "csv":
        gen = CSVGenerator()
        return gen.generate(project, detail="full")
    if fmt == "yaml":
        gen = YAMLGenerator()
        return gen.generate(project, detail="full")
    if fmt == "markdown":
        gen = MarkdownHybridGenerator()
        spec = gen.generate(project)
        return spec.content
    if fmt == "json":
        gen = JSONGenerator()
        return gen.generate(project, detail="full")
    if fmt == "logicml":
        gen = LogicMLGenerator()
        spec = gen.generate(project)
        return spec.content
    if fmt == "toon":
        gen = TOONGenerator()
        return gen.generate(project, detail="full")
    return ""


def _generate_token_json(project: ProjectInfo) -> str:
    """Generate compact, token-friendly JSON spec (used by examples/11_token_benchmark.py)."""
    data = {
        "project": project.name,
        "files": project.total_files,
        "lines": project.total_lines,
        "modules": [],
    }

    for m in project.modules:
        module: dict = {
            "path": m.path,
            "language": m.language,
            "imports": m.imports[:10],
            "exports": m.exports[:10],
        }

        if m.classes:
            module["classes"] = []
            for c in m.classes[:20]:
                cls = {
                    "name": c.name,
                    "bases": c.bases,
                    "doc": (c.docstring[:80] if c.docstring else ""),
                    "properties": c.properties[:15],
                    "methods": [
                        {
                            "name": method.name,
                            "params": method.params[:5],
                            "returns": method.return_type or "None",
                            "doc": (method.intent[:50] if method.intent else ""),
                            "async": method.is_async,
                        }
                        for method in c.methods[:15]
                    ],
                }
                module["classes"].append(cls)

        if m.functions:
            module["functions"] = [
                {
                    "name": f.name,
                    "params": f.params[:6],
                    "returns": f.return_type or "None",
                    "doc": (f.intent[:60] if f.intent else ""),
                    "async": f.is_async,
                    "lines": f.lines,
                }
                for f in m.functions[:20]
            ]

        data["modules"].append(module)

    return json.dumps(data, indent=2)


def _generate_token_json_compact(project: ProjectInfo) -> str:
    data = json.loads(_generate_token_json(project))
    return json.dumps(data, separators=(",", ":"))


def generate_spec_token(project: ProjectInfo, fmt: str) -> str:
    """Generate spec optimized for token benchmark (keeps historical behavior).

    Notes:
    - json/json_compact use the token-friendly JSON representation.
    - other formats delegate to generate_spec.
    """
    if fmt == "json":
        return _generate_token_json(project)
    if fmt == "json_compact":
        return _generate_token_json_compact(project)
    return generate_spec(project, fmt)


def get_async_reproduction_prompt(
    spec: str, fmt: str, file_name: str, with_tests: bool = False
) -> str:
    base_prompts = {
        "gherkin": f"""Generate Python code from this Gherkin/BDD specification.
Implement all scenarios as working, production-ready code.

{spec[:6000]}

Requirements:
- Generate complete, working Python code for {file_name}
- Include all imports
- Use type hints
- Add docstrings""",
        "yaml": f"""Generate Python code from this YAML specification.
Match the structure exactly with all classes and functions.

{spec[:6000]}

Requirements:
- Generate complete, working Python code for {file_name}
- Include all imports
- Use type hints
- Implement all methods with actual logic""",
        "markdown": f"""Generate Python code from this Markdown specification.
It contains embedded Gherkin (behaviors) and YAML (structures).

{spec[:6000]}

Requirements:
- Generate complete, working Python code for {file_name}
- Include all imports
- Implement all classes and functions
- Use type hints throughout""",
    }

    prompt = base_prompts.get(fmt, base_prompts["yaml"])

    if with_tests:
        prompt += """

IMPORTANT: Also generate a unittest test class at the end of the file.
Include tests for each function/method with at least 2 test cases each.
Use unittest.TestCase as base class.
Name the test class Test<ClassName> or TestFunctions."""

    return prompt


def get_token_reproduction_prompt(
    spec: str, fmt: str, file_name: str, language: str = "python"
) -> str:
    format_hints = {
        "json": """Parse the JSON structure carefully:
- 'modules' array contains file-level info with 'classes' and 'functions'
- Each class has 'name', 'bases', 'methods' with full signatures
- Each function has 'name', 'params', 'returns', 'doc'
- Implement ALL classes with their methods and ALL standalone functions
- Use the 'doc' field to implement actual logic, not just stubs
CRITICAL: Match every class/function name and signature exactly.""",
        "json_compact": "Parse the compact JSON and implement all elements with exact signatures.",
        "yaml": """Parse the YAML structure carefully:
- Top-level keys describe modules with classes and functions
- Each class has 'bases', 'properties', 'methods' with signatures
- Each function has params, return type, and docstring/intent
- Implement ALL classes, methods, and standalone functions
- Use intent/docstring to write actual logic, not placeholders
CRITICAL: Match every name and signature exactly as specified.""",
        "gherkin": """Parse Gherkin/BDD specification and reconstruct the ORIGINAL source code:
- 'Feature:' = a class or module (use the name after Feature)
- 'Scenario:' = a function or method to implement
- 'Given' steps = setup / preconditions / imports needed
- 'When' steps = the core action / logic to implement
- 'Then' steps = expected outcomes / return values / assertions
- 'And' continues the previous step type
- '@tag' annotations may indicate decorators or categories

IMPORTANT RULES:
1. Each Scenario becomes a real function with actual logic (NOT test code)
2. Given/When/Then describe behavior, translate them to implementation
3. Include all imports mentioned in Given steps
4. Use type hints based on parameter descriptions
5. Implement real logic based on When/Then steps, not just stubs
6. If a Feature has multiple Scenarios, they are methods of the same class""",
        "markdown": """Parse the Markdown specification to reconstruct source code:
- '## Module' or '### Class' headings define code structure
- Embedded YAML blocks describe attributes, methods, signatures
- Embedded Gherkin blocks describe behaviors to implement
- Code blocks show example usage or signatures
- Tables may list functions with their parameters and return types

IMPORTANT RULES:
1. Extract class names, method signatures, and function signatures from headings and YAML
2. Implement all listed methods with actual logic based on descriptions
3. Include all imports mentioned anywhere in the document
4. Use type hints from signatures or parameter descriptions
5. Docstrings should come from the description text""",
        "logicml": """Parse LogicML and generate VALID, complete code:
- 'module:' = file to generate
- 'sig:' lines = EXACT function signatures (translate to target language)
- 'does:' = function intent/docstring — use this to implement real logic
- 'type: re-export' = module primarily re-exports symbols from imports
- 'attrs:' = instance attributes to initialize in __init__/constructor
- 'bases:' = parent classes to inherit from
- 'decorators:' = decorators to apply
- 'calls:' = other functions this function calls (implement the call chain)
- 'raises:' = exceptions this function may raise

CRITICAL RULES:
1. Translate EVERY 'sig:' line into a real function with actual logic
2. Use 'does:' text to implement meaningful function bodies
3. Ensure valid syntax - balanced brackets, proper indentation
4. Include ALL imports listed in the module""",
        "toon": """Parse TOON (Token-Oriented Object Notation) format carefully:

STRUCTURE:
- 'imports[N]: mod1,mod2' = import statements to include
- 'classes[N]{name,bases,decorators,props,methods}:' = class definitions
- 'functions[N]{name,sig,decorators,async,category,lines}:' = function definitions
- 'function_docs:' section = docstrings/intent for each function

SIGNATURE FORMAT '(params)->ReturnType':
- 'sig: (self;x: int;y: str)->bool' = def func(self, x: int, y: str) -> bool
- 'sig: (self)->None' = def func(self) -> None
- Semicolons separate params, '->' indicates return type

DECORATORS:
- 'decorators: @property' = add @property decorator
- 'decorators: @staticmethod|@cache' = multiple decorators

CRITICAL RULES:
1. Use imports[] to generate all import statements
2. Use function_docs to write real function bodies (not stubs)
3. Match exact signatures from sig: fields
4. Include ALL classes with their methods and ALL standalone functions
5. Preserve async functions (marked with 'async: true')""",
        "csv": """Parse the CSV table to reconstruct source code:
- Columns: path, type, name, signature, language, intent, category, domain, imports
- 'type=class' rows define classes (look at 'bases' if present)
- 'type=method' rows are methods of the preceding class
- 'type=function' rows are standalone functions
- 'signature' column has the exact function signature to use
- 'intent' column describes what the function does — use it to implement real logic
- 'imports' column lists required imports

IMPORTANT RULES:
1. Group methods under their parent class
2. Include all imports from the 'imports' column
3. Match signatures exactly as shown
4. Use 'intent' to implement actual logic, not just stubs
5. Add type hints based on signature information""",
        "function.toon": """Parse the function-logic TOON format to reconstruct source code:
- 'modules[N]{path,lang,items}:' lists source files and their function count
- 'function_details:' contains per-module function listings as tables
- Table columns: line, name, sig[, does, decorators, calls, raises]
- 'ClassName.method_name' = this is a method of ClassName (create the class)
- '~function_name' = async function (add async keyword)
- 'cc:N' suffix on name = cyclomatic complexity hint (more complex logic needed)
- 'sig' column has exact signature: (params)->ReturnType

CRITICAL RULES:
1. Create classes for any ClassName that appears as prefix in 'ClassName.method'
2. Translate EVERY listed function into real code with actual logic
3. Use 'does' column text to implement meaningful function bodies
4. Match signatures EXACTLY from the 'sig' column
5. Include imports needed for the types and calls referenced
6. Preserve method grouping under their classes""",
    }

    # Language-specific guidance appended to prompt
    lang_hints = {
        "javascript": "Use ES6+ syntax (const/let, arrow functions, classes). Use module.exports or export.",
        "typescript": "Use TypeScript syntax with interfaces, type annotations, and export statements.",
        "go": "Use proper Go syntax: package declaration, func receivers for methods, error returns.",
        "rust": "Use proper Rust syntax: impl blocks for methods, pub fn, Result/Option types, ownership.",
        "java": "Use proper Java syntax: public class, access modifiers, typed parameters, semicolons.",
        "csharp": "Use proper C# syntax: namespaces, access modifiers, typed parameters, semicolons.",
        "sql": "Use standard SQL: CREATE TABLE/VIEW/FUNCTION, proper column types, constraints.",
    }

    max_spec = 12000
    spec_truncated = spec[:max_spec] if len(spec) > max_spec else spec

    language_norm = (language or "python").strip().lower()
    lang_label_map = {
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "go": "Go",
        "rust": "Rust",
        "java": "Java",
        "csharp": "C#",
        "sql": "SQL",
    }
    lang_label = lang_label_map.get(language_norm, language_norm)

    lang_hint = lang_hints.get(language_norm, "")
    lang_hint_line = f"\n{lang_hint}" if lang_hint else ""

    prompt = f"""Generate complete {lang_label} source code from this {fmt.upper()} specification.
{format_hints.get(fmt, "")}{lang_hint_line}

SPECIFICATION:
{spec_truncated}

REQUIREMENTS:
- Output complete, working {lang_label} code for {file_name}
- Include ALL imports at the top
- Implement ALL classes, methods, and functions listed in the specification
- Use type hints throughout
- Write real logic based on descriptions/intents, NOT placeholder stubs
- Match function signatures EXACTLY as specified
- Output ONLY the code, no explanations

```{language_norm}
"""
    return prompt


def get_simple_reproduction_prompt(spec: str, fmt: str, file_name: str) -> str:
    prompts = {
        "gherkin": f"""Generate Python code from this Gherkin/BDD specification.
Implement all scenarios as working code.

{spec[:5000]}

Generate complete Python code for {file_name}:""",
        "yaml": f"""Generate Python code from this YAML specification.
Match the structure exactly.

{spec[:5000]}

Generate complete Python code for {file_name}:""",
        "markdown": f"""Generate Python code from this Markdown specification.
It contains embedded Gherkin and YAML sections.

{spec[:5000]}

Generate complete Python code for {file_name}:""",
        "logicml": f"""Generate Python code from this LogicML specification.
'sig:' = EXACT function signature, 'does:' = docstring, 'attrs:' = class attributes.
Match signatures EXACTLY.

{spec[:5000]}

Generate complete Python code for {file_name}:""",
    }

    return prompts.get(fmt, prompts["yaml"])
