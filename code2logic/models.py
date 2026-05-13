"""
Data models for Code2Logic.
- DependencyNode: Dependency graph node with metrics
- ProjectInfo: Complete project analysis results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FunctionInfo:
    """Information about a function or method.

    Attributes:
        name: Function name
        params: List of parameter strings (e.g., ["x:int", "y:str"])
        return_type: Return type annotation if available
        docstring: First line of docstring
        calls: List of function calls made within this function
        raises: List of exceptions raised
        complexity: Cyclomatic complexity estimate
        lines: Number of lines in the function
        decorators: List of decorator names
        is_async: Whether function is async
        is_static: Whether function is static method
        is_private: Whether function is private (starts with _)
        intent: Generated intent/purpose description
        start_line: Starting line number in source
        end_line: Ending line number in source
    """

    name: str
    params: List[str]
    return_type: Optional[str]
    docstring: Optional[str]
    calls: List[str]
    raises: List[str]
    complexity: int
    lines: int
    decorators: List[str]
    is_async: bool
    is_static: bool
    is_private: bool
    intent: str
    start_line: int = 0
    end_line: int = 0


@dataclass
class ClassInfo:
    """Information about a class or interface.

    Attributes:
        name: Class name
        bases: List of base class names
        docstring: First line of docstring
        methods: List of methods in the class
        properties: List of property/attribute names
        is_interface: Whether this is an interface (TypeScript)
        is_abstract: Whether this is an abstract class
        generic_params: List of generic type parameters
        is_dataclass: Whether this is a dataclass (@dataclass decorator)
    """

    name: str
    bases: List[str]
    docstring: Optional[str]
    methods: List[FunctionInfo]
    properties: List[str]
    is_interface: bool
    is_abstract: bool
    generic_params: List[str]
    is_dataclass: bool = False


@dataclass
class TypeInfo:
    """Information about a type alias, interface, or enum.

    Attributes:
        name: Type name
        kind: Type kind ('type', 'interface', 'enum', 'struct', 'trait')
        definition: Short definition string
    """

    name: str
    kind: str  # 'type', 'interface', 'enum', 'struct', 'trait'
    definition: str
    values: Optional[List[str]] = None


@dataclass
class ModuleInfo:
    """Information about a source file/module.

    Attributes:
        path: Relative path to the file
        language: Programming language
        imports: List of import statements
        exports: List of exported symbols
        classes: List of classes in the module
        functions: List of top-level functions
        types: List of type definitions
        constants: List of constant metadata
        docstring: Module docstring
        lines_total: Total line count
        lines_code: Lines of actual code (excluding comments/blanks)
    """

    path: str
    language: str
    imports: List[str]
    exports: List[str]
    classes: List[ClassInfo]
    functions: List[FunctionInfo]
    types: List[TypeInfo]
    constants: List[ConstantInfo]
    docstring: Optional[str]
    lines_total: int
    lines_code: int


@dataclass
class DependencyNode:
    """Node in the dependency graph with metrics.

    Attributes:
        path: Module path
        in_degree: Number of incoming dependencies
        out_degree: Number of outgoing dependencies
        pagerank: PageRank score (importance metric)
        is_hub: Whether this is a hub module (high centrality)
        cluster: Cluster ID for grouping related modules
    """

    path: str
    in_degree: int = 0
    out_degree: int = 0
    pagerank: float = 0.0
    is_hub: bool = False
    cluster: int = 0


@dataclass
class ProjectInfo:
    """Complete project analysis results.

    Attributes:
        name: Project name (directory name)
        root_path: Absolute path to project root
        languages: Dict mapping language to file count
        modules: List of all analyzed modules
        dependency_graph: Dict mapping module path to list of dependencies
        dependency_metrics: Dict mapping module path to DependencyNode
        entrypoints: List of detected entry point files
        similar_functions: Dict mapping function to list of similar functions
        total_files: Total number of analyzed files
        total_lines: Total line count across all files
        generated_at: ISO timestamp of analysis
    """

    name: str
    root_path: str
    languages: Dict[str, int]
    modules: List[ModuleInfo]
    dependency_graph: Dict[str, List[str]]
    dependency_metrics: Dict[str, DependencyNode]
    entrypoints: List[str]
    similar_functions: Dict[str, List[str]]
    total_files: int
    total_lines: int
    total_bytes: int = 0
    generated_at: str = ""


# Backwards compatibility aliases for tests
Project = ProjectInfo
Module = ModuleInfo
Function = FunctionInfo
Class = ClassInfo


@dataclass
class ConstantInfo:
    """Module-level constant information."""

    name: str
    type_annotation: str = ""
    value: Optional[str] = None
    value_keys: Optional[List[str]] = (
        None  # For dicts - just keys to avoid size explosion
    )


@dataclass
class FieldInfo:
    """Dataclass field information."""

    name: str
    type_annotation: str
    default: Optional[str] = None
    default_factory: Optional[str] = None


@dataclass
class AttributeInfo:
    """Instance attribute information (self.x = ...)."""

    name: str
    type_annotation: str = ""
    set_in_init: bool = True


@dataclass
class PropertyInfo:
    """Property information (@property, @x.setter)."""

    name: str
    type_annotation: str = ""
    has_getter: bool = False
    has_setter: bool = False
    docstring: str = ""


@dataclass
class OptionalImport:
    """Try/except import block information."""

    module: str
    from_module: Optional[str] = None
    imports: List[str] = field(default_factory=list)
    flag_name: str = ""
    fallback_value: bool = False


@dataclass
class ClassInfo:
    """Information about a class or interface.

    Attributes:
        name: Class name
        bases: List of base class names
        decorators: List of decorators applied to the class
        docstring: First line of docstring
        is_dataclass: Whether this is a dataclass (@dataclass decorator)
        fields: List of dataclass fields (for dataclasses only)
        attributes: List of instance attributes
        properties: List of @property definitions
        methods: List of methods in the class
        is_interface: Whether this is an interface (TypeScript)
        is_abstract: Whether this is an abstract class
        generic_params: List of generic type parameters
    """

    name: str
    bases: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    is_dataclass: bool = False
    fields: List[FieldInfo] = field(default_factory=list)
    attributes: List[AttributeInfo] = field(default_factory=list)
    properties: List[PropertyInfo] = field(default_factory=list)
    methods: List[FunctionInfo] = field(default_factory=list)
    is_interface: bool = False
    is_abstract: bool = False
    generic_params: List[str] = field(default_factory=list)


@dataclass
class FunctionInfo:
    """Information about a function or method.

    Attributes:
        name: Function name
        params: List of parameter strings (without defaults for backward compatibility)
        params_with_defaults: Dict mapping param names to default values
        return_type: Return type annotation
        docstring: Function docstring
        docstring_full: Full docstring (optional, for detailed analysis)
        calls: List of function calls made within this function
        raises: List of exceptions that can be raised
        decorators: List of decorators applied to the function
        complexity: Cyclomatic complexity score
        lines: Number of lines in function
        is_async: Whether this is an async function
        is_static: Whether this is a @staticmethod
        is_classmethod: Whether this is a @classmethod
        is_property: Whether this is a @property getter
        intent: Inferred intent/description
        start_line: Line number where function starts
        end_line: Line number where function ends
    """

    name: str
    params: List[str] = field(default_factory=list)
    params_with_defaults: Dict[str, str] = field(default_factory=dict)
    return_type: str = ""
    docstring: Optional[str] = None
    docstring_full: Optional[str] = None
    calls: List[str] = field(default_factory=list)
    raises: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    complexity: int = 1
    lines: int = 0
    is_async: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    intent: str = ""
    start_line: int = 0
    end_line: int = 0
    is_private: bool = False


@dataclass
class ModuleInfo:
    """Information about a source file/module.

    Attributes:
        path: Relative path to the file
        language: Programming language
        imports: List of import statements
        exports: List of exported symbols
        constants: List of module-level constants
        type_checking_imports: List of TYPE_CHECKING imports
        optional_imports: List of try/except import blocks
        aliases: Dict mapping aliases to real names
        classes: List of classes in the module
        functions: List of top-level functions
        types: List of type definitions
        docstring: Module docstring
        lines_total: Total line count
        lines_code: Lines of actual code (excluding comments/blanks)
        file_bytes: Size of the source file in bytes
    """

    path: str
    language: str = "python"
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    constants: List[ConstantInfo] = field(default_factory=list)
    type_checking_imports: List[str] = field(default_factory=list)
    optional_imports: List[OptionalImport] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    types: List[TypeInfo] = field(default_factory=list)
    docstring: Optional[str] = None
    lines_total: int = 0
    lines_code: int = 0
    file_bytes: int = 0
