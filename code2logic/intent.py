"""
Enhanced Intent Generator with NLP support.

Uses lemmatization, pattern matching, and docstring extraction
to generate human-readable intent descriptions for functions.
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    pass


class IntentType(Enum):
    """Types of user intents for code analysis."""

    REFACTOR = auto()
    ANALYZE = auto()
    OPTIMIZE = auto()
    DEBUG = auto()
    DOCUMENT = auto()
    TEST = auto()


@dataclass
class Intent:
    """Represents a detected user intent."""

    type: IntentType
    confidence: float
    target: str
    description: str
    suggestions: List[str] = field(default_factory=list)


# Optional NLP imports with graceful degradation
try:
    import nltk
    from nltk.stem import WordNetLemmatizer

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    import spacy

    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


class EnhancedIntentGenerator:
    """
    Generator intencji z NLP - lemmatyzacja, ekstrakcja z docstringów.

    Supports both English and Polish intent generation.
    Falls back gracefully if NLP libraries are not available.

    Example:
        >>> gen = EnhancedIntentGenerator(lang='en')
        >>> gen.generate("getUserById", "Fetches a user by their ID")
        'retrieves user by id'
        >>> gen.generate("validateEmail")
        'validates email'
    """

    # Extended verb patterns (PL + EN)
    VERB_PATTERNS: dict[tuple[str, ...], tuple[str, str]] = {
        # CRUD operations
        ("get", "fetch", "retrieve", "load", "find", "query", "read", "select"): (
            "pobiera",
            "retrieves",
        ),
        ("set", "update", "modify", "change", "edit", "put", "patch"): (
            "aktualizuje",
            "updates",
        ),
        (
            "create",
            "make",
            "build",
            "generate",
            "new",
            "add",
            "insert",
            "post",
            "init",
        ): ("tworzy", "creates"),
        ("delete", "remove", "clear", "destroy", "drop", "erase"): ("usuwa", "deletes"),
        # Validation
        ("is", "has", "can", "should", "check", "test", "assert"): (
            "sprawdza",
            "checks",
        ),
        ("validate", "verify", "confirm", "authenticate"): ("waliduje", "validates"),
        # Transformation
        ("convert", "transform", "map", "translate", "cast", "to"): (
            "konwertuje",
            "converts",
        ),
        ("parse", "extract", "decode", "deserialize"): ("parsuje", "parses"),
        ("format", "render", "serialize", "encode", "stringify"): (
            "formatuje",
            "formats",
        ),
        # Communication
        ("send", "emit", "dispatch", "publish", "notify", "push"): ("wysyła", "sends"),
        ("receive", "listen", "subscribe", "on", "handle"): ("obsługuje", "handles"),
        # Lifecycle
        ("init", "initialize", "setup", "configure", "bootstrap"): (
            "inicjalizuje",
            "initializes",
        ),
        ("start", "run", "execute", "launch", "begin", "open"): ("uruchamia", "starts"),
        ("stop", "end", "finish", "close", "shutdown", "terminate"): (
            "kończy",
            "stops",
        ),
        # Data operations
        ("process", "compute", "calculate", "evaluate", "analyze"): (
            "przetwarza",
            "processes",
        ),
        ("filter", "search", "match", "lookup"): ("filtruje", "filters"),
        ("sort", "order", "arrange", "rank"): ("sortuje", "sorts"),
        ("merge", "combine", "join", "concat"): ("łączy", "merges"),
        ("split", "divide", "separate", "partition"): ("dzieli", "splits"),
        # Logging
        ("log", "print", "write", "output", "display"): ("loguje", "logs"),
        # Registration
        ("register", "bind", "attach", "connect", "hook"): ("rejestruje", "registers"),
        # Caching
        ("cache", "memoize", "store", "save", "persist"): ("cachuje", "caches"),
    }

    def __init__(self, lang: str = "en"):
        """
        Initialize the intent generator.

        Args:
            lang: Language for intent output ('en' or 'pl')
        """
        self.lang = lang
        self.lemmatizer = None
        self.nlp = None

        # Initialize NLTK lemmatizer if available
        if NLTK_AVAILABLE:
            try:
                nltk.data.find("corpora/wordnet")
                self.lemmatizer = WordNetLemmatizer()
            except LookupError:
                try:
                    nltk.download("wordnet", quiet=True)
                    self.lemmatizer = WordNetLemmatizer()
                except Exception:
                    pass

        # Initialize spaCy if available (for more advanced NLP)
        if SPACY_AVAILABLE:
            try:
                model = "pl_core_news_sm" if lang == "pl" else "en_core_web_sm"
                self.nlp = spacy.load(model)
            except OSError:
                try:
                    self.nlp = spacy.load("en_core_web_sm")
                except OSError:
                    pass

    def generate(self, name: str, docstring: Optional[str] = None) -> str:
        """
        Generate intent from function name and optional docstring.

        Args:
            name: Function or method name
            docstring: Optional docstring to extract intent from

        Returns:
            Human-readable intent description

        Example:
            >>> gen = EnhancedIntentGenerator()
            >>> gen.generate("calculateTotalPrice")
            'processes total price'
        """
        # Try docstring first
        if docstring:
            intent = self._extract_from_docstring(docstring)
            if intent and len(intent) >= 10:
                return intent[:80]

        # Parse function name
        words = self._split_name(name)
        if not words:
            return name

        first_word = words[0].lower()
        rest = " ".join(words[1:]).lower() if len(words) > 1 else ""

        # Lemmatize if available
        if self.lemmatizer:
            try:
                first_word = self.lemmatizer.lemmatize(first_word, pos="v")
            except Exception:
                pass

        # Match against verb patterns
        intent_idx = 0 if self.lang == "pl" else 1
        for verbs, intents in self.VERB_PATTERNS.items():
            if first_word in verbs:
                intent = intents[intent_idx]
                return f"{intent} {rest}" if rest else intent

        # Fallback - join words
        return " ".join(words).lower()

    def _extract_from_docstring(self, docstring: str) -> Optional[str]:
        """Extract intent from docstring's first line."""
        if not docstring:
            return None

        first_line = docstring.split("\n")[0].strip()

        # Remove common prefixes
        prefixes = [
            "Returns",
            "Return",
            "Gets",
            "Get",
            "Sets",
            "Set",
            "Creates",
            "Create",
            "Deletes",
            "Delete",
            "The",
            "A",
            "An",
        ]
        for prefix in prefixes:
            if first_line.startswith(prefix + " "):
                first_line = first_line[len(prefix) + 1 :]
                break

        return first_line[:80] if first_line else None

    def _split_name(self, name: str) -> List[str]:
        """
        Split function name into words.

        Handles:
        - camelCase
        - PascalCase
        - snake_case
        - kebab-case
        - ACRONYMS (e.g., XMLParser -> XML Parser)
        """
        # Remove private prefixes
        name = name.lstrip("_").lstrip("#")

        # Handle kebab-case
        name = name.replace("-", "_")

        # snake_case
        if "_" in name:
            return [w for w in name.split("_") if w]

        # camelCase/PascalCase with acronym support
        # XMLParser -> XML Parser, parseXML -> parse XML
        words = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
        words = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", words)

        return [w.strip() for w in words.split() if w.strip()]

    @classmethod
    def get_available_features(cls) -> dict[str, bool]:
        """
        Get dictionary of available NLP features.

        Returns:
            Dict with feature names and availability status
        """
        return {
            "nltk_lemmatizer": NLTK_AVAILABLE,
            "spacy": SPACY_AVAILABLE,
        }


class IntentAnalyzer:
    """
    Analyzes user queries to detect intent and provide suggestions.

    Used for understanding what the user wants to do with the code
    (refactor, analyze, optimize, etc.) and providing relevant suggestions.
    """

    def __init__(self):
        """Initialize the intent analyzer with patterns."""
        self.intent_patterns = {
            IntentType.REFACTOR: [
                "refactor",
                "restructure",
                "improve",
                "clean",
                "reorganize",
                "simplify",
            ],
            IntentType.ANALYZE: [
                "analyze",
                "explain",
                "understand",
                "describe",
                "show",
                "structure",
            ],
            IntentType.OPTIMIZE: [
                "optimize",
                "performance",
                "speed",
                "fast",
                "efficient",
                "memory",
            ],
            IntentType.DEBUG: ["debug", "fix", "bug", "error", "issue", "problem"],
            IntentType.DOCUMENT: [
                "document",
                "comment",
                "docstring",
                "readme",
                "documentation",
            ],
            IntentType.TEST: ["test", "coverage", "unittest", "pytest", "testing"],
        }
        self.code_smell_patterns = {
            "long_module": 500,
            "complex_function": 10,
            "large_class": 15,
            "too_many_imports": 20,
        }

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from a query string."""
        # Simple word extraction, filtering common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "to",
            "and",
            "or",
            "in",
            "of",
            "for",
            "is",
            "it",
            "this",
            "that",
            "i",
        }
        words = re.findall(r"\b\w+\b", query.lower())
        return [w for w in words if w not in stop_words]

    def _calculate_intent_confidence(
        self, keywords: List[str], patterns: List[str]
    ) -> float:
        """Calculate confidence score based on keyword matches."""
        if not patterns:
            return 0.0
        matches = sum(1 for k in keywords if k in patterns)
        return matches / len(patterns)

    def _identify_target(self, query: str, project: Any) -> str:
        """Identify the target of the query (module, function, class, or project)."""
        query_lower = query.lower()

        # Check for module names
        for module in project.modules:
            module_name = getattr(module, "name", None) or module.path.split("/")[
                -1
            ].replace(".py", "")
            if module_name.lower() in query_lower:
                # Check for function within module
                for func in module.functions:
                    if func.name.lower() in query_lower:
                        return f"{module_name}.{func.name}"
                # Check for class within module
                for cls in module.classes:
                    if cls.name.lower() in query_lower:
                        return f"{module_name}.{cls.name}"
                return module_name

        return "project"

    def _generate_description(self, intent_type: IntentType, target: str) -> str:
        """Generate a description for the detected intent."""
        descriptions = {
            IntentType.REFACTOR: f"Refactoring suggestions for {target}",
            IntentType.ANALYZE: f"Analysis of {target}",
            IntentType.OPTIMIZE: f"Performance optimization for {target}",
            IntentType.DEBUG: f"Debugging assistance for {target}",
            IntentType.DOCUMENT: f"Documentation suggestions for {target}",
            IntentType.TEST: f"Testing suggestions for {target}",
        }
        return descriptions.get(intent_type, f"Analysis of {target}")

    def _generate_suggestions(
        self, intent_type: IntentType, target: str, project: Any
    ) -> List[str]:
        """Generate suggestions based on intent type."""
        suggestions = {
            IntentType.REFACTOR: [
                "Review dependency structure",
                "Consider extracting common functionality",
                "Look for duplicate code patterns",
            ],
            IntentType.ANALYZE: [
                "Review dependency graph",
                "Check module structure",
                "Examine function complexity",
            ],
            IntentType.OPTIMIZE: [
                "Profile performance bottlenecks",
                "Review algorithmic complexity",
                "Consider caching strategies",
            ],
            IntentType.DEBUG: [
                "Add logging statements",
                "Review error handling",
                "Check edge cases",
            ],
            IntentType.DOCUMENT: [
                "Add module docstrings",
                "Document public APIs",
                "Create usage examples",
            ],
            IntentType.TEST: [
                "Add unit tests",
                "Improve test coverage",
                "Add integration tests",
            ],
        }
        return suggestions.get(intent_type, [])

    def analyze_intent(self, query: str, project: Any) -> List[Intent]:
        """
        Analyze a query and return detected intents sorted by confidence.

        Args:
            query: User query string
            project: Project model to analyze against

        Returns:
            List of Intent objects sorted by confidence (descending)
        """
        keywords = self._extract_keywords(query)
        target = self._identify_target(query, project)
        intents = []

        for intent_type, patterns in self.intent_patterns.items():
            confidence = self._calculate_intent_confidence(keywords, patterns)
            if confidence > 0:
                description = self._generate_description(intent_type, target)
                suggestions = self._generate_suggestions(intent_type, target, project)
                intents.append(
                    Intent(
                        type=intent_type,
                        confidence=confidence,
                        target=target,
                        description=description,
                        suggestions=suggestions,
                    )
                )

        # Sort by confidence descending
        intents.sort(key=lambda x: x.confidence, reverse=True)
        return intents

    def detect_code_smells(self, project: Any) -> List[dict]:
        """
        Detect code smells in the project.

        Args:
            project: Project model to analyze

        Returns:
            List of detected code smells
        """
        smells = []

        for module in project.modules:
            module_name = getattr(module, "name", None) or module.path.split("/")[
                -1
            ].replace(".py", "")
            lines = getattr(module, "lines_of_code", None) or getattr(
                module, "lines_total", 0
            )

            # Check for long module
            if lines > self.code_smell_patterns["long_module"]:
                smells.append(
                    {
                        "type": "long_module",
                        "target": module_name,
                        "message": f"Module has {lines} lines (threshold: {self.code_smell_patterns['long_module']})",
                    }
                )

            # Check for too many imports
            if len(module.imports) > self.code_smell_patterns["too_many_imports"]:
                smells.append(
                    {
                        "type": "too_many_imports",
                        "target": module_name,
                        "message": f"Module has {len(module.imports)} imports",
                    }
                )

            # Check functions
            for func in module.functions:
                complexity = getattr(func, "complexity", 1)
                if complexity > self.code_smell_patterns["complex_function"]:
                    smells.append(
                        {
                            "type": "complex_function",
                            "target": f"{module_name}.{func.name}",
                            "message": f"Function has complexity {complexity}",
                        }
                    )

            # Check classes
            for cls in module.classes:
                if len(cls.methods) > self.code_smell_patterns["large_class"]:
                    smells.append(
                        {
                            "type": "large_class",
                            "target": f"{module_name}.{cls.name}",
                            "message": f"Class has {len(cls.methods)} methods",
                        }
                    )

        return smells

    def suggest_refactoring(self, target: str, project: Any) -> List[str]:
        """
        Generate refactoring suggestions for a target.

        Args:
            target: Target identifier (module, module.class, module.function)
            project: Project model

        Returns:
            List of refactoring suggestions
        """
        obj = self._find_target_object(target, project)
        if obj is None:
            return ["Target not found"]

        # Check object type and delegate
        if hasattr(obj, "functions") and hasattr(obj, "classes"):
            return self._suggest_module_refactoring(obj)
        elif hasattr(obj, "methods"):
            return self._suggest_class_refactoring(obj)
        elif hasattr(obj, "complexity"):
            return self._suggest_function_refactoring(obj)

        return []

    def _find_target_object(self, target: str, project: Any) -> Any:
        """Find the object referenced by target string."""
        parts = target.split(".")

        for module in project.modules:
            module_name = getattr(module, "name", None) or module.path.split("/")[
                -1
            ].replace(".py", "")
            if module_name == parts[0]:
                if len(parts) == 1:
                    return module
                # Look for function or class
                for func in module.functions:
                    if func.name == parts[1]:
                        return func
                for cls in module.classes:
                    if cls.name == parts[1]:
                        return cls
        return None

    def _suggest_module_refactoring(self, module: Any) -> List[str]:
        """Generate refactoring suggestions for a module."""
        suggestions = []

        if len(module.functions) > 20:
            suggestions.append(
                "Consider splitting this module into smaller, focused modules"
            )

        if len(module.imports) > 15:
            suggestions.append("Review imports and consider consolidating dependencies")

        lines = getattr(module, "lines_of_code", None) or getattr(
            module, "lines_total", 0
        )
        if lines > 400:
            suggestions.append(
                "Module is large; consider extracting related functions into submodules"
            )

        return suggestions or ["Module structure looks reasonable"]

    def _suggest_class_refactoring(self, cls: Any) -> List[str]:
        """Generate refactoring suggestions for a class."""
        suggestions = []

        if len(cls.methods) > 15:
            suggestions.append(
                "Consider splitting class into smaller classes with focused responsibilities"
            )

        bases = getattr(cls, "base_classes", []) or getattr(cls, "bases", [])
        if len(bases) > 3:
            suggestions.append(
                "Consider using composition over inheritance to reduce coupling"
            )

        return suggestions or ["Class structure looks reasonable"]

    def _suggest_function_refactoring(self, func: Any) -> List[str]:
        """Generate refactoring suggestions for a function."""
        suggestions = []

        lines = getattr(func, "lines_of_code", None) or getattr(func, "lines", 0)
        if lines > 50:
            suggestions.append(
                "Consider breaking this function into smaller helper functions"
            )

        complexity = getattr(func, "complexity", 1)
        if complexity > 10:
            suggestions.append(
                "High cyclomatic complexity; consider simplifying control flow"
            )

        params = getattr(func, "parameters", []) or getattr(func, "params", [])
        if len(params) > 5:
            suggestions.append(
                "Many parameters; consider using a parameter object or builder pattern"
            )

        if not getattr(func, "docstring", None):
            suggestions.append("Add a docstring to document the function's purpose")

        return suggestions or ["Function structure looks reasonable"]


# Alias for backwards compatibility
ProjectAnalyzer = IntentAnalyzer
