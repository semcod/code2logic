"""
Markdown Hybrid Format Generator for Code2Logic.

Optimized hybrid format based on benchmark insights:
- YAML for structures (60% structural score) - classes, dataclasses, types
- Gherkin for behaviors (83% semantic score) - functions, methods, logic
- Compact metadata for imports and dependencies

Benchmark results show:
- YAML best for: structural matching, text similarity
- Gherkin best for: semantic preservation, success rate
- Combined: better overall reproduction quality
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .generators import YAMLGenerator
from .gherkin import GherkinGenerator
from .models import ProjectInfo


@dataclass
class MarkdownSpec:
    """Markdown specification for a project."""

    content: str
    file_count: int
    total_chars: int
    sections: Dict[str, int]  # section name -> char count


class MarkdownHybridGenerator:
    """
    Generates optimized Markdown hybrid format.

    Combines:
    - File tree (compact overview)
    - Gherkin (behaviors/functions)
    - YAML (data structures/classes)
    - Metadata (imports, dependencies)
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.gherkin_gen = GherkinGenerator()
        self.yaml_gen = YAMLGenerator()

    def generate(self, project: ProjectInfo, detail: str = "full") -> MarkdownSpec:
        """Generate Markdown hybrid specification."""
        sections = {}
        parts = []

        # Header
        header = self._generate_header(project)
        parts.append(header)
        sections["header"] = len(header)

        # File tree
        tree = self._generate_tree(project)
        parts.append(tree)
        sections["tree"] = len(tree)

        # Imports summary
        imports = self._generate_imports(project)
        parts.append(imports)
        sections["imports"] = len(imports)

        # Classes as YAML
        classes_yaml = self._generate_classes_yaml(project)
        parts.append(classes_yaml)
        sections["classes"] = len(classes_yaml)

        # Functions as Gherkin
        functions_gherkin = self._generate_functions_gherkin(project)
        parts.append(functions_gherkin)
        sections["functions"] = len(functions_gherkin)

        # Dependencies
        deps = self._generate_dependencies(project)
        parts.append(deps)
        sections["dependencies"] = len(deps)

        content = "\n".join(parts)

        return MarkdownSpec(
            content=content,
            file_count=len(project.modules),
            total_chars=len(content),
            sections=sections,
        )

    def _generate_header(self, project: ProjectInfo) -> str:
        """Generate header section."""
        return f"""# {project.name} - Logic Specification

> Auto-generated hybrid format for code reproduction
> Files: {len(project.modules)} | Classes: {sum(len(m.classes) for m in project.modules)} | Functions: {sum(len(m.functions) for m in project.modules)}

"""

    def _generate_tree(self, project: ProjectInfo) -> str:
        """Generate file tree section."""
        lines = ["## 📁 File Structure\n", "```"]

        # Group by directory
        dirs: Dict[str, List[str]] = {}
        for module in project.modules:
            path = Path(module.path)
            dir_name = str(path.parent) if path.parent != Path(".") else "."
            if dir_name not in dirs:
                dirs[dir_name] = []
            dirs[dir_name].append(path.name)

        for dir_name, files in sorted(dirs.items()):
            if dir_name != ".":
                lines.append(f"{dir_name}/")
            for f in sorted(files):
                prefix = "  " if dir_name != "." else ""
                lines.append(f"{prefix}├── {f}")

        lines.append("```\n")
        return "\n".join(lines)

    def _generate_imports(self, project: ProjectInfo) -> str:
        """Generate imports as YAML for precise reproduction."""
        lines = ["## 📦 Imports (YAML)\n"]
        lines.append("```yaml")
        lines.append("# Required imports for code reproduction")

        for module in project.modules:
            if module.imports:
                lines.append(f"\n{Path(module.path).name}:")

                # Categorize
                stdlib_modules = {
                    "os",
                    "sys",
                    "json",
                    "typing",
                    "pathlib",
                    "dataclasses",
                    "re",
                    "ast",
                    "abc",
                    "collections",
                    "functools",
                    "itertools",
                    "datetime",
                    "logging",
                    "argparse",
                    "subprocess",
                    "shutil",
                    "time",
                    "copy",
                    "io",
                    "contextlib",
                    "enum",
                    "hashlib",
                }

                stdlib = []
                third_party = []
                local = []

                for imp in module.imports:
                    base = imp.split(".")[0]
                    if base in stdlib_modules:
                        stdlib.append(imp)
                    elif imp.startswith("."):
                        local.append(imp)
                    else:
                        third_party.append(imp)

                if stdlib:
                    lines.append(f"  stdlib: [{', '.join(sorted(set(stdlib))[:10])}]")
                if third_party:
                    lines.append(
                        f"  third_party: [{', '.join(sorted(set(third_party))[:10])}]"
                    )
                if local:
                    lines.append(f"  local: [{', '.join(sorted(set(local))[:5])}]")

        lines.append("```\n")
        return "\n".join(lines)

    def _generate_classes_yaml(self, project: ProjectInfo) -> str:
        """Generate classes as detailed YAML codeblock.

        YAML is best for structural reproduction (60% benchmark score).
        Include full type information and signatures for better LLM reproduction.
        """
        lines = ["## 🏗️ Data Structures (YAML)\n"]
        lines.append("```yaml")
        lines.append("# Classes and dataclasses - use @dataclass decorator where noted")

        has_classes = False
        for module in project.modules:
            if module.classes:
                has_classes = True
                lines.append(f"\n# File: {Path(module.path).name}")

                for cls in module.classes:
                    # Check if dataclass
                    is_dataclass = (
                        any(
                            "dataclass" in d
                            for d in cls.methods[0].decorators
                            if cls.methods
                        )
                        if cls.methods
                        else False
                    )
                    is_dataclass = is_dataclass or "dataclass" in str(cls.bases)

                    lines.append(f"\n{cls.name}:")

                    # Type annotation
                    if is_dataclass:
                        lines.append("  type: dataclass")
                    elif cls.is_abstract:
                        lines.append("  type: abstract_class")
                    elif cls.is_interface:
                        lines.append("  type: interface")
                    else:
                        lines.append("  type: class")

                    # Docstring
                    if cls.docstring:
                        doc = cls.docstring.split("\n")[0][:80]
                        lines.append(f'  doc: "{doc}"')

                    # Inheritance
                    if cls.bases:
                        lines.append(f"  bases: [{', '.join(cls.bases)}]")

                    # Properties with types (important for reproduction)
                    if cls.properties:
                        lines.append("  fields:")
                        for prop in cls.properties[:15]:
                            # Try to extract type from property string
                            if ":" in prop:
                                name, type_hint = prop.split(":", 1)
                                lines.append(f"    {name.strip()}: {type_hint.strip()}")
                            else:
                                lines.append(f"    {prop}: Any")

                    # Methods with signatures
                    if cls.methods:
                        lines.append("  methods:")
                        for method in cls.methods[:15]:
                            # Build full signature
                            params = ", ".join(method.params[:5])
                            ret = method.return_type or "None"
                            decorators = (
                                ", ".join(method.decorators[:2])
                                if method.decorators
                                else ""
                            )

                            method_info = f"{method.name}({params}) -> {ret}"
                            if decorators:
                                method_info = f"@{decorators} {method_info}"
                            if method.is_async:
                                method_info = f"async {method_info}"

                            lines.append(f"    - {method_info}")

        if not has_classes:
            lines.append("# No classes defined")

        lines.append("```\n")
        return "\n".join(lines)

    def _generate_functions_gherkin(self, project: ProjectInfo) -> str:
        """Generate functions as detailed Gherkin codeblock.

        Gherkin is best for semantic reproduction (83% benchmark score).
        Include full behavioral descriptions for better LLM understanding.
        """
        lines = ["## ⚡ Functions & Behaviors (Gherkin)\n"]
        lines.append("```gherkin")
        lines.append("# Function behaviors and logic - implement as Python functions")

        has_functions = False
        for module in project.modules:
            # Only top-level functions (methods handled in YAML)
            all_funcs = list(module.functions)

            if all_funcs:
                has_functions = True
                lines.append(f"\nFeature: {Path(module.path).stem}")
                if module.docstring:
                    lines.append(f"  # {module.docstring.split(chr(10))[0][:60]}")

                for func in all_funcs[:20]:
                    lines.append(f"\n  @{func.name}")

                    # Async marker
                    if func.is_async:
                        lines.append("  @async")

                    # Decorators
                    for dec in func.decorators[:3]:
                        lines.append(f"  @{dec}")

                    lines.append(f"  Scenario: {func.name}")

                    # Docstring as description
                    if func.docstring:
                        doc = func.docstring.split("\n")[0][:70]
                        lines.append(f'    """{doc}"""')

                    # Parameters with types
                    if func.params:
                        for param in func.params[:6]:
                            if ":" in param:
                                name, ptype = param.split(":", 1)
                                lines.append(
                                    f"    Given parameter {name.strip()}: {ptype.strip()}"
                                )
                            else:
                                lines.append(f"    Given parameter {param}")
                    else:
                        lines.append("    Given no parameters")

                    # Function calls (behavior)
                    if func.calls:
                        for call in func.calls[:5]:
                            lines.append(f"    When calls {call}")

                    # Exceptions
                    if func.raises:
                        for exc in func.raises[:3]:
                            lines.append(f"    And may raise {exc}")

                    # Return type
                    if func.return_type and func.return_type != "None":
                        lines.append(f"    Then returns {func.return_type}")
                    else:
                        lines.append("    Then returns None")

        if not has_functions:
            lines.append("# No top-level functions defined")

        lines.append("```\n")
        return "\n".join(lines)

    def _generate_dependencies(self, project: ProjectInfo) -> str:
        """Generate module dependencies section."""
        lines = ["## 🔗 Module Dependencies\n"]

        # Build dependency graph
        deps = {}
        for module in project.modules:
            name = Path(module.path).stem
            local_deps = [
                imp
                for imp in module.imports
                if imp.startswith(".")
                or any(imp.startswith(Path(m.path).stem) for m in project.modules)
            ]
            if local_deps:
                deps[name] = local_deps[:5]

        if deps:
            lines.append("```")
            for module, imports in sorted(deps.items()):
                lines.append(f"{module} -> {', '.join(imports)}")
            lines.append("```\n")
        else:
            lines.append("*No internal dependencies*\n")

        return "\n".join(lines)


def generate_markdown_hybrid(project: ProjectInfo, detail: str = "full") -> str:
    """Convenience function to generate Markdown hybrid format."""
    generator = MarkdownHybridGenerator()
    spec = generator.generate(project, detail)
    return spec.content


def generate_file_markdown(file_path: str) -> str:
    """Generate Markdown hybrid for a single file."""
    from .analyzer import ProjectAnalyzer

    path = Path(file_path)
    analyzer = ProjectAnalyzer()
    project = analyzer.analyze(str(path.parent))

    # Filter to just this file
    target_name = path.name
    project.modules = [m for m in project.modules if Path(m.path).name == target_name]

    generator = MarkdownHybridGenerator()
    spec = generator.generate(project)
    return spec.content
