"""
Code Reproducer - Generate code files from logic specifications.

Provides:
- File reproduction from YAML/JSON specs
- Structure validation
- Selective file validation
- Comparison with original files
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

CONSTANT_50 = 50.0
CONSTANT_80 = 80


def _safe_load_yaml_file(path: str) -> Any:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "pyyaml is required for YAML specs. Install: pip install pyyaml"
        ) from e
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class ReproductionStatus(Enum):
    """Status of file reproduction."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileValidation:
    """Validation result for a single file."""

    path: str
    exists: bool = False
    syntax_ok: bool = False
    structure_match: bool = False
    classes_match: int = 0
    classes_expected: int = 0
    functions_match: int = 0
    functions_expected: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Calculate match score 0-100."""
        if not self.exists:
            return 0.0

        total = self.classes_expected + self.functions_expected
        matched = self.classes_match + self.functions_match

        if total == 0:
            return 100.0 if self.syntax_ok else CONSTANT_50

        base_score = (matched / total) * 100
        if not self.syntax_ok:
            base_score *= 0.5

        return round(base_score, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "syntax_ok": self.syntax_ok,
            "score": self.score,
            "classes": f"{self.classes_match}/{self.classes_expected}",
            "functions": f"{self.functions_match}/{self.functions_expected}",
            "errors": self.errors,
        }


@dataclass
class ReproductionResult:
    """Result of reproduction process."""

    output_dir: str
    total_files: int = 0
    generated_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    validations: List[FileValidation] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return round((self.generated_files / self.total_files) * 100, 1)

    @property
    def average_score(self) -> float:
        if not self.validations:
            return 0.0
        return round(sum(v.score for v in self.validations) / len(self.validations), 1)

    def summary(self) -> str:
        lines = [
            "Reproduction Result:",
            f"  Output: {self.output_dir}",
            f"  Files: {self.generated_files}/{self.total_files} generated",
            f"  Success Rate: {self.success_rate}%",
            f"  Average Score: {self.average_score}%",
        ]
        if self.failed_files:
            lines.append(f"  Failed: {self.failed_files}")
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
        return "\n".join(lines)


class SpecReproducer:
    """
    Reproduces code structure from logic specifications.

    Usage:
        reproducer = SpecReproducer()
        result = reproducer.reproduce_from_yaml(
            spec_path="/path/to/spec.yaml",
            output_dir="/path/to/output"
        )
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def reproduce_from_yaml(
        self,
        spec_path: str,
        output_dir: str,
        filter_paths: Optional[List[str]] = None,
    ) -> ReproductionResult:
        """
        Reproduce files from YAML specification.

        Args:
            spec_path: Path to YAML spec file
            output_dir: Directory to write generated files
            filter_paths: Optional list of paths to reproduce (selective)
        """
        spec = _safe_load_yaml_file(spec_path)

        return self._reproduce(spec, output_dir, filter_paths)

    def reproduce_from_json(
        self,
        spec_path: str,
        output_dir: str,
        filter_paths: Optional[List[str]] = None,
    ) -> ReproductionResult:
        """Reproduce files from JSON specification."""
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)

        return self._reproduce(spec, output_dir, filter_paths)

    def _reproduce(
        self,
        spec: Dict[str, Any],
        output_dir: str,
        filter_paths: Optional[List[str]] = None,
    ) -> ReproductionResult:
        """Internal reproduction logic."""
        result = ReproductionResult(output_dir=output_dir)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        modules = spec.get("modules", [])
        result.total_files = len(modules)

        for module in modules:
            path = module.get("path", "")

            # Apply filter if specified
            if filter_paths:
                if not any(f in path for f in filter_paths):
                    result.skipped_files += 1
                    continue

            try:
                generated = self._generate_file(module, output_path)
                if generated:
                    result.generated_files += 1
                    if self.verbose:
                        print(f"  ✓ {path}")
                else:
                    result.failed_files += 1
                    if self.verbose:
                        print(f"  ✗ {path}")
            except Exception as e:
                result.failed_files += 1
                result.errors.append(f"{path}: {str(e)}")
                if self.verbose:
                    print(f"  ✗ {path}: {e}")

        return result

    def _generate_file(self, module: Dict[str, Any], output_path: Path) -> bool:
        """Generate a single file from module spec."""
        path = module.get("path", "")
        language = module.get("language", "python")

        file_path = output_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if language == "python":
            content = self._generate_python(module)
        elif language in ("typescript", "javascript"):
            content = self._generate_typescript(module)
        else:
            content = f"// Unsupported language: {language}\n"

        file_path.write_text(content, encoding="utf-8")
        return True

    def _generate_python(self, module: Dict[str, Any]) -> str:
        """Generate Python file content."""
        lines = ['"""']
        lines.append(f"Generated from: {module.get('path', 'unknown')}")
        lines.append('"""')
        lines.append("")

        # Imports
        imports = module.get("imports", [])
        if imports:
            # Group imports
            std_imports = []
            from_imports = {}

            for imp in imports:
                if "." in imp:
                    parts = imp.rsplit(".", 1)
                    mod = parts[0]
                    name = parts[1] if len(parts) > 1 else imp
                    if mod not in from_imports:
                        from_imports[mod] = []
                    from_imports[mod].append(name)
                else:
                    std_imports.append(imp)

            for imp in std_imports:
                lines.append(f"import {imp}")

            for mod, names in from_imports.items():
                lines.append(f"from {mod} import {', '.join(names)}")

            lines.append("")

        # Classes
        classes = module.get("classes", [])
        for cls in classes:
            lines.extend(self._generate_python_class(cls))
            lines.append("")

        # Functions
        functions = module.get("functions", [])
        for func in functions:
            lines.extend(self._generate_python_function(func))
            lines.append("")

        return "\n".join(lines)

    def _render_docstring(self, text: str, indent: str) -> List[str]:
        """Render a safe Python docstring or fall back to comments."""
        if not text:
            return []

        s = str(text).replace("\r\n", "\n").replace("\r", "\n")

        # Choose delimiter that doesn't appear in content
        if "'''" not in s:
            delim = "'''"
        elif '"""' not in s:
            delim = '"""'
        else:
            # Worst-case fallback: comments (always safe)
            out = []
            for line in s.splitlines():
                out.append(f"{indent}# {line}" if line else f"{indent}#")
            return out

        # Multi-line docstring
        if "\n" in s:
            out = [f"{indent}{delim}"]
            out.extend([f"{indent}{line}" for line in s.splitlines()])
            out.append(f"{indent}{delim}")
            return out

        # Single-line docstring
        return [f"{indent}{delim}{s}{delim}"]

    def _sanitize_python_property(self, prop: str) -> str:
        """Sanitize a Python class property declaration for valid syntax."""
        if not prop:
            return ""

        s = str(prop).strip()

        # Fix Literal[...] values by quoting items if needed.
        # Example: Literal[CASCADE,SET NULL] -> Literal["CASCADE","SET NULL"]
        def _fix_literal(match: re.Match) -> str:
            inner = match.group(1)
            items = [p.strip() for p in inner.split(",") if p.strip()]
            fixed = []
            for it in items:
                if it.startswith(('"', "'")) and it.endswith(('"', "'")):
                    fixed.append(it)
                    continue
                if it in {"None", "True", "False"}:
                    fixed.append(it)
                    continue
                if re.fullmatch(r"-?\d+(?:\.\d+)?", it):
                    fixed.append(it)
                    continue
                # Quote everything else (identifiers, hyphenated, spaced, etc.)
                fixed.append('"' + it.replace('"', '\\"') + '"')
            return f"Literal[{', '.join(fixed)}]"

        s = re.sub(r"Literal\[([^\]]*)\]", _fix_literal, s)
        return s

    def _generate_python_class(self, cls: Dict[str, Any]) -> List[str]:
        """Generate Python class."""
        lines = []

        name = cls.get("name", "UnnamedClass")
        bases = cls.get("bases", [])
        docstring = cls.get("docstring", "")

        # Class declaration
        if bases:
            lines.append(f"class {name}({', '.join(bases)}):")
        else:
            lines.append(f"class {name}:")

        # Docstring
        if docstring:
            lines.extend(self._render_docstring(docstring, indent="    "))

        # Properties
        properties = cls.get("properties", [])
        if properties:
            lines.append("    ")
            for prop in properties:
                prop_decl = self._sanitize_python_property(prop)
                if not prop_decl:
                    continue
                if "=" in prop_decl:
                    lines.append(f"    {prop_decl}")
                else:
                    lines.append(f"    {prop_decl} = None")

        # Methods
        methods = cls.get("methods", [])
        if methods:
            for method in methods:
                lines.append("")
                for line in self._generate_python_method(method):
                    lines.append(f"    {line}")
        elif not properties:
            lines.append("    pass")

        return lines

    def _generate_python_method(self, method: Dict[str, Any]) -> List[str]:
        """Generate Python method."""
        lines = []

        name = method.get("name", "unnamed")
        signature = method.get("signature", "(self)")
        intent = method.get("intent", "")
        is_async = method.get("is_async", False)

        # Parse signature
        sig = self._parse_signature(signature)

        # Method declaration
        prefix = "async " if is_async else ""
        lines.append(f"{prefix}def {name}{sig}:")

        # Docstring
        if intent:
            lines.extend(self._render_docstring(intent, indent="    "))

        # Body placeholder
        if is_async:
            lines.append("    pass  # TODO: implement")
        else:
            lines.append("    pass  # TODO: implement")

        return lines

    def _generate_python_function(self, func: Dict[str, Any]) -> List[str]:
        """Generate Python function."""
        lines = []

        name = func.get("name", "unnamed")
        signature = func.get("signature", "()")
        intent = func.get("intent", "")
        is_async = func.get("is_async", False)

        sig = self._parse_signature(signature)

        prefix = "async " if is_async else ""
        lines.append(f"{prefix}def {name}{sig}:")

        if intent:
            lines.extend(self._render_docstring(intent, indent="    "))

        lines.append("    pass  # TODO: implement")

        return lines

    def _generate_typescript(self, module: Dict[str, Any]) -> str:
        """Generate TypeScript file content."""
        lines = ["/**"]
        lines.append(f" * Generated from: {module.get('path', 'unknown')}")
        lines.append(" */")
        lines.append("")

        # Exports
        exports = module.get("exports", [])

        # Classes
        classes = module.get("classes", [])
        for cls in classes:
            lines.extend(self._generate_ts_class(cls))
            lines.append("")

        # Functions
        functions = module.get("functions", [])
        for func in functions:
            lines.extend(self._generate_ts_function(func))
            lines.append("")

        # Export statement if needed
        if exports:
            export_names = [e for e in exports if e not in ["default"]]
            if export_names:
                lines.append(f"export {{ {', '.join(export_names)} }};")

        return "\n".join(lines)

    def _generate_ts_class(self, cls: Dict[str, Any]) -> List[str]:
        """Generate TypeScript class."""
        lines = []

        name = cls.get("name", "UnnamedClass")
        bases = cls.get("bases", [])
        docstring = cls.get("docstring", "")

        if docstring:
            lines.append(f"/** {docstring} */")

        extends = f" extends {bases[0]}" if bases else ""
        lines.append(f"export class {name}{extends} {{")

        # Methods
        methods = cls.get("methods", [])
        for method in methods:
            lines.append("")
            for line in self._generate_ts_method(method):
                lines.append(f"  {line}")

        lines.append("}")
        return lines

    def _generate_ts_method(self, method: Dict[str, Any]) -> List[str]:
        """Generate TypeScript method."""
        lines = []

        name = method.get("name", "unnamed")
        signature = method.get("signature", "()")
        is_async = method.get("is_async", False)

        prefix = "async " if is_async else ""
        lines.append(f"{prefix}{name}{signature} {{")
        lines.append("    // TODO: implement")
        lines.append("}")

        return lines

    def _generate_ts_function(self, func: Dict[str, Any]) -> List[str]:
        """Generate TypeScript function."""
        lines = []

        name = func.get("name", "unnamed")
        signature = func.get("signature", "()")
        is_async = func.get("is_async", False)

        prefix = "async " if is_async else ""
        lines.append(f"export {prefix}function {name}{signature} {{")
        lines.append("  // TODO: implement")
        lines.append("}")

        return lines

    def _parse_signature(self, sig: str) -> str:
        """Parse and clean signature."""
        sig = sig.strip()
        if not sig.startswith("("):
            sig = "(" + sig
        if ")" not in sig:
            sig = sig + ")"

        # Extract just params and return
        if "->" in sig:
            parts = sig.split("->")
            params = parts[0].strip()
            ret = parts[1].strip()
            return f"{params} -> {ret}"

        return sig.split(")")[0] + ")"


class SpecValidator:
    """
    Validates generated files against logic specification.

    Usage:
        validator = SpecValidator()
        results = validator.validate(
            spec_path="/path/to/spec.yaml",
            generated_dir="/path/to/generated",
            filter_paths=["models/", "utils/"]
        )
    """

    def __init__(self):
        pass

    def validate(
        self,
        spec_path: str,
        generated_dir: str,
        filter_paths: Optional[List[str]] = None,
    ) -> List[FileValidation]:
        """
        Validate generated files against spec.

        Args:
            spec_path: Path to YAML/JSON spec
            generated_dir: Directory with generated files
            filter_paths: Optional list of paths to validate (selective)
        """
        # Load spec
        if spec_path.endswith(".json"):
            with open(spec_path) as f:
                spec = json.load(f)
        else:
            spec = _safe_load_yaml_file(spec_path)

        results = []
        generated_path = Path(generated_dir)

        for module in spec.get("modules", []):
            path = module.get("path", "")

            # Apply filter
            if filter_paths:
                if not any(f in path for f in filter_paths):
                    continue

            validation = self._validate_file(module, generated_path)
            results.append(validation)

        return results

    def _validate_file(self, module: Dict[str, Any], base_path: Path) -> FileValidation:
        """Validate a single file."""
        path = module.get("path", "")
        file_path = base_path / path

        validation = FileValidation(path=path)

        # Check existence
        if not file_path.exists():
            validation.errors.append("File not found")
            return validation

        validation.exists = True

        # Read content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            validation.errors.append(f"Read error: {e}")
            return validation

        # Check syntax
        language = module.get("language", "python")
        if language == "python":
            validation.syntax_ok = self._check_python_syntax(content, validation)
        else:
            validation.syntax_ok = True  # Skip for other languages

        # Check structure
        expected_classes = module.get("classes", [])
        expected_functions = module.get("functions", [])

        validation.classes_expected = len(expected_classes)
        validation.functions_expected = len(expected_functions)

        # Count matches
        for cls in expected_classes:
            cls_name = cls.get("name", "")
            if f"class {cls_name}" in content:
                validation.classes_match += 1

        for func in expected_functions:
            func_name = func.get("name", "")
            if f"def {func_name}" in content or f"function {func_name}" in content:
                validation.functions_match += 1

        validation.structure_match = (
            validation.classes_match == validation.classes_expected
            and validation.functions_match == validation.functions_expected
        )

        return validation

    def _check_python_syntax(self, content: str, validation: FileValidation) -> bool:
        """Check Python syntax."""
        try:
            compile(content, "<string>", "exec")
            return True
        except SyntaxError as e:
            validation.errors.append(f"Syntax error: {e}")
            return False


def reproduce_project(
    spec_path: str,
    output_dir: str,
    filter_paths: Optional[List[str]] = None,
    validate: bool = True,
    verbose: bool = True,
) -> ReproductionResult:
    """
    Convenience function to reproduce and validate a project.

    Args:
        spec_path: Path to YAML/JSON spec
        output_dir: Output directory for generated files
        filter_paths: Optional filter for selective reproduction
        validate: Whether to validate after reproduction
        verbose: Print progress

    Returns:
        ReproductionResult with validation data
    """
    if verbose:
        print(f"Reproducing from: {spec_path}")
        print(f"Output to: {output_dir}")
        if filter_paths:
            print(f"Filter: {filter_paths}")
        print()

    reproducer = SpecReproducer(verbose=verbose)

    if spec_path.endswith(".json"):
        result = reproducer.reproduce_from_json(spec_path, output_dir, filter_paths)
    else:
        result = reproducer.reproduce_from_yaml(spec_path, output_dir, filter_paths)

    if validate:
        if verbose:
            print()
            print("Validating generated files...")

        validator = SpecValidator()
        validations = validator.validate(spec_path, output_dir, filter_paths)
        result.validations = validations

        if verbose:
            for v in validations:
                status = (
                    "✓"
                    if v.score >= CONSTANT_80
                    else "○"
                    if v.score >= CONSTANT_50
                    else "✗"
                )
                print(f"  {status} {v.path}: {v.score}%")

    if verbose:
        print()
        print(result.summary())

    return result


def validate_files(
    spec_path: str,
    generated_dir: str,
    filter_paths: Optional[List[str]] = None,
) -> List[FileValidation]:
    """
    Validate specific files against spec.

    Args:
        spec_path: Path to YAML/JSON spec
        generated_dir: Directory with generated files
        filter_paths: Paths to validate (e.g., ["models/", "user.py"])

    Returns:
        List of FileValidation results
    """
    validator = SpecValidator()
    return validator.validate(spec_path, generated_dir, filter_paths)
