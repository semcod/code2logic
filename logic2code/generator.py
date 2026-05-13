"""
Main code generator that orchestrates parsing and code generation.
"""

# Import from sibling package
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

sys.path.insert(0, str(Path(__file__).parent.parent))

from logic2test.parsers import LogicParser, ModuleSpec, ProjectSpec

from .renderers import PythonRenderer, RenderConfig


@dataclass
class GeneratorConfig:
    """Configuration for code generation."""

    language: str = "python"
    stubs_only: bool = False
    include_docstrings: bool = True
    include_type_hints: bool = True
    generate_init: bool = True
    preserve_structure: bool = True
    output_suffix: str = ""
    use_llm: bool = False  # Use LLM to generate implementations
    llm_provider: Optional[str] = None  # LLM provider (auto, openrouter, ollama, etc.)


@dataclass
class GenerationResult:
    """Result of code generation."""

    files_generated: int = 0
    classes_generated: int = 0
    functions_generated: int = 0
    lines_generated: int = 0
    output_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class CodeGenerator:
    """
    Main code generator class.

    Reads Code2Logic output files and generates source code.

    Usage:
        generator = CodeGenerator('project.c2l.yaml')
        result = generator.generate('output/')
        print(f"Generated {result.files_generated} files")
    """

    def __init__(self, logic_file: Union[str, Path], config: Optional[GeneratorConfig] = None):
        """
        Initialize code generator.

        Args:
            logic_file: Path to Code2Logic output file (YAML, Hybrid, or TOON)
            config: Optional configuration for generation
        """
        self.logic_file = Path(logic_file)
        self.config = config or GeneratorConfig()
        self._project: Optional[ProjectSpec] = None
        self._llm_client = None

        # Initialize LLM client if requested
        if self.config.use_llm:
            try:
                from lolm import get_client

                self._llm_client = get_client(provider=self.config.llm_provider)
            except ImportError:
                pass  # LLM not available
            except Exception:
                pass  # LLM initialization failed

        # Set up renderer based on language
        render_config = RenderConfig(
            include_docstrings=self.config.include_docstrings,
            include_type_hints=self.config.include_type_hints,
            stubs_only=self.config.stubs_only,
        )

        if self.config.language == "python":
            self.renderer = PythonRenderer(render_config)
        else:
            raise ValueError(f"Unsupported language: {self.config.language}")

    @property
    def project(self) -> ProjectSpec:
        """Lazy-load and cache project spec."""
        if self._project is None:
            parser = LogicParser(self.logic_file)
            self._project = parser.parse()
        return self._project

    def generate(
        self, output_dir: Union[str, Path], modules: Optional[List[str]] = None
    ) -> GenerationResult:
        """
        Generate code for the project.

        Args:
            output_dir: Directory to write generated files
            modules: Optional list of module paths to generate
                    (None = all modules)

        Returns:
            GenerationResult with statistics
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        result = GenerationResult()
        generated_modules: List[ModuleSpec] = []

        for module in self.project.modules:
            # Filter modules if specified
            if modules:
                if not any(m in module.path for m in modules):
                    continue

            # Skip non-matching language modules
            if module.language != self.config.language:
                continue

            try:
                code = self.generate_module(module.path)

                if code.strip():
                    # Generate output filename
                    output_file = self._get_output_path(output_path, module.path)
                    output_file.parent.mkdir(parents=True, exist_ok=True)

                    output_file.write_text(code, encoding="utf-8")

                    result.files_generated += 1
                    result.classes_generated += len(module.classes)
                    result.functions_generated += len(module.functions)
                    result.lines_generated += code.count("\n")
                    result.output_files.append(str(output_file))
                    generated_modules.append(module)

            except Exception as e:
                result.errors.append(f"Error processing {module.path}: {e}")

        # Generate __init__.py if configured
        if self.config.generate_init and generated_modules:
            try:
                init_code = self.renderer.render_init_file(generated_modules)
                init_path = output_path / "__init__.py"
                init_path.write_text(init_code, encoding="utf-8")
                result.files_generated += 1
                result.output_files.append(str(init_path))
            except Exception as e:
                result.errors.append(f"Error generating __init__.py: {e}")

        return result

    def generate_module(self, module_path: str) -> str:
        """
        Generate code for a single module.

        Args:
            module_path: Path to the module (as in logic file)

        Returns:
            Generated source code as string
        """
        # Find the module
        module = None
        for m in self.project.modules:
            if m.path == module_path or module_path in m.path:
                module = m
                break

        if module is None:
            raise ValueError(f"Module not found: {module_path}")

        return self.renderer.render_module(module)

    def generate_class(self, class_name: str, module_path: Optional[str] = None) -> str:
        """
        Generate code for a single class.

        Args:
            class_name: Name of the class
            module_path: Optional module path to narrow search

        Returns:
            Generated class code as string
        """
        for module in self.project.modules:
            if module_path and module_path not in module.path:
                continue

            for cls in module.classes:
                if cls.name == class_name:
                    return self.renderer.render_class(cls)

        raise ValueError(f"Class not found: {class_name}")

    def generate_function(self, func_name: str, module_path: Optional[str] = None) -> str:
        """
        Generate code for a single function.

        Args:
            func_name: Name of the function
            module_path: Optional module path to narrow search

        Returns:
            Generated function code as string
        """
        for module in self.project.modules:
            if module_path and module_path not in module.path:
                continue

            for func in module.functions:
                if func.name == func_name:
                    return self.renderer.render_function(func)

        raise ValueError(f"Function not found: {func_name}")

    def _get_output_path(self, output_dir: Path, module_path: str) -> Path:
        """Generate output file path from module path."""
        path = Path(module_path)

        if self.config.preserve_structure:
            # Preserve directory structure
            output_file = output_dir / path
        else:
            # Flat structure
            output_file = output_dir / path.name

        # Add suffix if configured
        if self.config.output_suffix:
            stem = output_file.stem
            output_file = output_file.with_name(
                f"{stem}{self.config.output_suffix}{output_file.suffix}"
            )

        return output_file

    def summary(self) -> Dict:
        """Get summary of what can be generated."""
        total_classes = 0
        total_functions = 0
        total_methods = 0
        dataclasses_count = 0

        python_modules = 0
        other_modules = 0

        for module in self.project.modules:
            if module.language == "python":
                python_modules += 1
            else:
                other_modules += 1

            for cls in module.classes:
                total_classes += 1
                if cls.is_dataclass:
                    dataclasses_count += 1
                total_methods += len(cls.methods)

            total_functions += len(module.functions)

        return {
            "project_name": self.project.name,
            "total_modules": len(self.project.modules),
            "python_modules": python_modules,
            "other_modules": other_modules,
            "total_classes": total_classes,
            "total_functions": total_functions,
            "total_methods": total_methods,
            "dataclasses": dataclasses_count,
        }

    def list_modules(self) -> List[str]:
        """List all available module paths."""
        return [m.path for m in self.project.modules]

    def list_classes(self) -> List[str]:
        """List all available class names with their modules."""
        classes = []
        for module in self.project.modules:
            for cls in module.classes:
                classes.append(f"{module.path}::{cls.name}")
        return classes

    def list_functions(self) -> List[str]:
        """List all available function names with their modules."""
        functions = []
        for module in self.project.modules:
            for func in module.functions:
                functions.append(f"{module.path}::{func.name}")
        return functions
