"""
Advanced Metrics for Code Reproduction Quality.

Provides comprehensive analysis of reproduction quality with:
- Text similarity metrics (Levenshtein, Jaccard, cosine)
- Structural metrics (AST comparison, element matching)
- Semantic metrics (intent preservation, naming consistency)
- Format-specific metrics (compression, token efficiency)

Usage:
    from code2logic.metrics import ReproductionMetrics, analyze_reproduction

    metrics = ReproductionMetrics()
    result = metrics.analyze(original, generated)
"""

import difflib
import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple

# Configure logging
logger = logging.getLogger("code2logic.metrics")


@dataclass
class TextMetrics:
    """Text-level similarity metrics."""

    char_similarity: float = 0.0  # Character-level similarity
    line_similarity: float = 0.0  # Line-level similarity
    word_similarity: float = 0.0  # Word-level similarity
    levenshtein_ratio: float = 0.0  # Levenshtein distance ratio
    jaccard_similarity: float = 0.0  # Jaccard index (word sets)
    cosine_similarity: float = 0.0  # Cosine similarity (word vectors)

    diff_added: int = 0  # Lines added
    diff_removed: int = 0  # Lines removed
    diff_changed: int = 0  # Lines changed


@dataclass
class StructuralMetrics:
    """Structural code metrics."""

    classes_original: int = 0
    classes_generated: int = 0
    classes_match: bool = False

    functions_original: int = 0
    functions_generated: int = 0
    functions_match: bool = False

    methods_original: int = 0
    methods_generated: int = 0
    methods_match: bool = False

    imports_original: int = 0
    imports_generated: int = 0
    imports_match: bool = False

    attributes_original: int = 0
    attributes_generated: int = 0
    attributes_match: bool = False

    structural_score: float = 0.0  # Overall structural match %
    element_coverage: float = 0.0  # % of elements reproduced


@dataclass
class SemanticMetrics:
    """Semantic preservation metrics."""

    naming_similarity: float = 0.0  # How similar are identifier names
    docstring_present: float = 0.0  # % of docstrings preserved
    type_hints_present: float = 0.0  # % of type hints preserved
    decorator_match: float = 0.0  # % of decorators preserved
    signature_match: float = 0.0  # % of function signatures matching
    intent_score: float = 0.0  # Overall intent preservation


@dataclass
class FormatMetrics:
    """Format-specific efficiency metrics."""

    format_name: str = ""
    spec_chars: int = 0
    spec_lines: int = 0
    spec_tokens: int = 0  # Estimated tokens

    original_chars: int = 0
    generated_chars: int = 0

    compression_ratio: float = 0.0  # original / spec
    expansion_ratio: float = 0.0  # generated / spec
    efficiency_score: float = 0.0  # similarity / compression

    token_cost_estimate: float = 0.0  # Estimated API cost


@dataclass
class ReproductionResult:
    """Complete reproduction analysis result."""

    source_file: str = ""
    format_used: str = ""
    timestamp: str = ""

    text: TextMetrics = field(default_factory=TextMetrics)
    structural: StructuralMetrics = field(default_factory=StructuralMetrics)
    semantic: SemanticMetrics = field(default_factory=SemanticMetrics)
    format: FormatMetrics = field(default_factory=FormatMetrics)

    overall_score: float = 0.0  # Weighted overall score
    quality_grade: str = ""  # A, B, C, D, F

    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_report(self) -> str:
        """Generate detailed markdown report."""
        lines = [
            "# Reproduction Quality Report",
            "",
            f"**Source:** `{self.source_file}`",
            f"**Format:** {self.format_used}",
            f"**Grade:** {self.quality_grade} ({self.overall_score:.1f}%)",
            "",
            "## Text Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Character Similarity | {self.text.char_similarity:.1f}% |",
            f"| Line Similarity | {self.text.line_similarity:.1f}% |",
            f"| Word Similarity | {self.text.word_similarity:.1f}% |",
            f"| Levenshtein Ratio | {self.text.levenshtein_ratio:.1f}% |",
            f"| Jaccard Similarity | {self.text.jaccard_similarity:.1f}% |",
            f"| Cosine Similarity | {self.text.cosine_similarity:.1f}% |",
            "",
            "## Structural Metrics",
            "",
            "| Element | Original | Generated | Match |",
            "|---------|----------|-----------|-------|",
            f"| Classes | {self.structural.classes_original} | {self.structural.classes_generated} | {'✓' if self.structural.classes_match else '✗'} |",
            f"| Functions | {self.structural.functions_original} | {self.structural.functions_generated} | {'✓' if self.structural.functions_match else '✗'} |",
            f"| Methods | {self.structural.methods_original} | {self.structural.methods_generated} | {'✓' if self.structural.methods_match else '✗'} |",
            f"| Imports | {self.structural.imports_original} | {self.structural.imports_generated} | {'✓' if self.structural.imports_match else '✗'} |",
            f"| Attributes | {self.structural.attributes_original} | {self.structural.attributes_generated} | {'✓' if self.structural.attributes_match else '✗'} |",
            "",
            f"**Structural Score:** {self.structural.structural_score:.1f}%",
            f"**Element Coverage:** {self.structural.element_coverage:.1f}%",
            "",
            "## Semantic Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Naming Similarity | {self.semantic.naming_similarity:.1f}% |",
            f"| Docstrings Present | {self.semantic.docstring_present:.1f}% |",
            f"| Type Hints Present | {self.semantic.type_hints_present:.1f}% |",
            f"| Decorator Match | {self.semantic.decorator_match:.1f}% |",
            f"| Signature Match | {self.semantic.signature_match:.1f}% |",
            "",
            "## Format Efficiency",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Spec Size | {self.format.spec_chars} chars / {self.format.spec_tokens} tokens |",
            f"| Compression Ratio | {self.format.compression_ratio:.2f}x |",
            f"| Expansion Ratio | {self.format.expansion_ratio:.2f}x |",
            f"| Efficiency Score | {self.format.efficiency_score:.2f} |",
            "",
        ]

        if self.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


class ReproductionMetrics:
    """Analyze reproduction quality with multiple metrics."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        if verbose:
            logging.basicConfig(level=logging.DEBUG)

    def analyze(
        self,
        original: str,
        generated: str,
        spec: str = "",
        format_name: str = "",
        source_file: str = "",
    ) -> ReproductionResult:
        """Analyze reproduction quality.

        Args:
            original: Original source code
            generated: Generated code
            spec: Specification used (optional)
            format_name: Format name (optional)
            source_file: Source file name (optional)

        Returns:
            ReproductionResult with all metrics
        """
        logger.info(f"Analyzing reproduction quality for {source_file}")

        result = ReproductionResult(
            source_file=source_file,
            format_used=format_name,
        )

        # Text metrics
        logger.debug("Computing text metrics...")
        result.text = self._compute_text_metrics(original, generated)

        # Structural metrics
        logger.debug("Computing structural metrics...")
        result.structural = self._compute_structural_metrics(original, generated)

        # Semantic metrics
        logger.debug("Computing semantic metrics...")
        result.semantic = self._compute_semantic_metrics(original, generated)

        # Format metrics
        if spec:
            logger.debug("Computing format metrics...")
            result.format = self._compute_format_metrics(
                original, generated, spec, format_name
            )

        # Overall score
        result.overall_score = self._compute_overall_score(result)
        result.quality_grade = self._get_grade(result.overall_score)

        # Generate recommendations
        result.recommendations = self._generate_recommendations(result)

        logger.info(
            f"Analysis complete: {result.quality_grade} ({result.overall_score:.1f}%)"
        )

        return result

    def _compute_text_metrics(self, original: str, generated: str) -> TextMetrics:
        """Compute text-level metrics."""
        metrics = TextMetrics()

        # Normalize
        orig_lines = [l.rstrip() for l in original.split("\n") if l.strip()]
        gen_lines = [l.rstrip() for l in generated.split("\n") if l.strip()]

        orig_words = re.findall(r"\w+", original.lower())
        gen_words = re.findall(r"\w+", generated.lower())

        # Character similarity (SequenceMatcher)
        matcher = difflib.SequenceMatcher(None, original, generated)
        metrics.char_similarity = matcher.ratio() * 100

        # Line similarity
        line_matcher = difflib.SequenceMatcher(None, orig_lines, gen_lines)
        metrics.line_similarity = line_matcher.ratio() * 100

        # Word similarity
        word_matcher = difflib.SequenceMatcher(None, orig_words, gen_words)
        metrics.word_similarity = word_matcher.ratio() * 100

        # Levenshtein ratio (same as char similarity for SequenceMatcher)
        metrics.levenshtein_ratio = metrics.char_similarity

        # Jaccard similarity (word sets)
        orig_set = set(orig_words)
        gen_set = set(gen_words)
        intersection = len(orig_set & gen_set)
        union = len(orig_set | gen_set)
        metrics.jaccard_similarity = (intersection / union * 100) if union > 0 else 0

        # Cosine similarity (word frequency vectors)
        metrics.cosine_similarity = self._cosine_similarity(orig_words, gen_words)

        # Diff stats
        diff = list(difflib.unified_diff(orig_lines, gen_lines, lineterm=""))
        metrics.diff_added = sum(
            1 for d in diff if d.startswith("+") and not d.startswith("+++")
        )
        metrics.diff_removed = sum(
            1 for d in diff if d.startswith("-") and not d.startswith("---")
        )
        metrics.diff_changed = metrics.diff_added + metrics.diff_removed

        return metrics

    def _cosine_similarity(self, words1: List[str], words2: List[str]) -> float:
        """Compute cosine similarity between word lists."""
        counter1 = Counter(words1)
        counter2 = Counter(words2)

        all_words = set(counter1.keys()) | set(counter2.keys())

        dot_product = sum(counter1.get(w, 0) * counter2.get(w, 0) for w in all_words)
        magnitude1 = sum(v**2 for v in counter1.values()) ** 0.5
        magnitude2 = sum(v**2 for v in counter2.values()) ** 0.5

        if magnitude1 * magnitude2 == 0:
            return 0

        return (dot_product / (magnitude1 * magnitude2)) * 100

    def _compute_structural_metrics(
        self, original: str, generated: str
    ) -> StructuralMetrics:
        """Compute structural metrics using AST when possible, regex as fallback."""
        metrics = StructuralMetrics()

        orig = self._count_elements_ast(original)
        gen = self._count_elements_ast(generated)

        metrics.classes_original = orig["classes"]
        metrics.classes_generated = gen["classes"]
        metrics.classes_match = orig["classes"] == gen["classes"]

        metrics.functions_original = orig["functions"]
        metrics.functions_generated = gen["functions"]
        metrics.functions_match = orig["functions"] == gen["functions"]

        metrics.methods_original = orig["methods"]
        metrics.methods_generated = gen["methods"]
        metrics.methods_match = orig["methods"] == gen["methods"]

        metrics.imports_original = orig["imports"]
        metrics.imports_generated = gen["imports"]
        metrics.imports_match = orig["imports"] == gen["imports"]

        metrics.attributes_original = orig["attributes"]
        metrics.attributes_generated = gen["attributes"]
        metrics.attributes_match = orig["attributes"] == gen["attributes"]

        # Ratio-based structural score (partial credit instead of binary)
        total = 0.0
        for key in ("classes", "functions", "methods", "imports", "attributes"):
            ov, gv = orig[key], gen[key]
            if ov == 0 and gv == 0:
                total += 1.0
            elif max(ov, gv) > 0:
                total += min(ov, gv) / max(ov, gv)
        metrics.structural_score = (total / 5) * 100

        # Element coverage
        total_orig = sum(orig.values())
        total_gen = sum(gen.values())
        if total_orig > 0:
            metrics.element_coverage = min(total_gen / total_orig, 1.0) * 100

        return metrics

    @staticmethod
    def _count_elements_ast(code: str) -> Dict[str, int]:
        """Count structural elements using Python AST, with regex fallback."""
        import ast as _ast

        try:
            tree = _ast.parse(code)
        except SyntaxError:
            # Fallback to regex for unparseable code
            return {
                "classes": len(re.findall(r"^class\s+\w+", code, re.MULTILINE)),
                "functions": len(
                    re.findall(r"^(?:async\s+)?def\s+\w+", code, re.MULTILINE)
                ),
                "methods": len(
                    re.findall(r"^\s+(?:async\s+)?def\s+\w+", code, re.MULTILINE)
                ),
                "imports": len(re.findall(r"^(?:from|import)\s+", code, re.MULTILINE)),
                "attributes": len(
                    re.findall(r"^\s+\w+\s*(?::\s*[^=\n]+)?\s*=", code, re.MULTILINE)
                ),
            }

        classes = 0
        functions = 0
        methods = 0
        imports = 0
        attributes = 0

        for node in _ast.walk(tree):
            if isinstance(node, _ast.ClassDef):
                classes += 1
                # Count methods inside classes
                for item in node.body:
                    if isinstance(item, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                        methods += 1
                    # Count class-level attributes (annotated or assigned)
                    elif isinstance(item, (_ast.Assign, _ast.AnnAssign)):
                        attributes += 1
            elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                # Only count as top-level function if not inside a class
                # (methods already counted above)
                pass
            elif isinstance(node, (_ast.Import, _ast.ImportFrom)):
                imports += 1

        # Count top-level functions (not methods)
        for node in _ast.iter_child_nodes(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                functions += 1

        return {
            "classes": classes,
            "functions": functions,
            "methods": methods,
            "imports": imports,
            "attributes": attributes,
        }

    def _compute_semantic_metrics(
        self, original: str, generated: str
    ) -> SemanticMetrics:
        """Compute semantic preservation metrics."""
        metrics = SemanticMetrics()

        # Extract identifiers
        orig_identifiers = set(
            re.findall(r"\b([A-Z][a-z]+|[a-z_][a-z0-9_]*)\b", original)
        )
        gen_identifiers = set(
            re.findall(r"\b([A-Z][a-z]+|[a-z_][a-z0-9_]*)\b", generated)
        )

        # Naming similarity
        common = len(orig_identifiers & gen_identifiers)
        total = len(orig_identifiers | gen_identifiers)
        metrics.naming_similarity = (common / total * 100) if total > 0 else 0

        # Docstring presence
        orig_docstrings = len(re.findall(r'""".*?"""', original, re.DOTALL))
        gen_docstrings = len(re.findall(r'""".*?"""', generated, re.DOTALL))
        if orig_docstrings > 0:
            metrics.docstring_present = min(gen_docstrings / orig_docstrings, 1.0) * 100
        else:
            metrics.docstring_present = 100 if gen_docstrings == 0 else 50

        # Type hints presence
        orig_hints = len(re.findall(r":\s*\w+[\[\],\s\w]*(?:\s*=|$|\))", original))
        gen_hints = len(re.findall(r":\s*\w+[\[\],\s\w]*(?:\s*=|$|\))", generated))
        if orig_hints > 0:
            metrics.type_hints_present = min(gen_hints / orig_hints, 1.0) * 100
        else:
            metrics.type_hints_present = 100

        # Decorator match
        orig_decorators = set(re.findall(r"@\w+", original))
        gen_decorators = set(re.findall(r"@\w+", generated))
        if orig_decorators:
            common_dec = len(orig_decorators & gen_decorators)
            metrics.decorator_match = (common_dec / len(orig_decorators)) * 100
        else:
            metrics.decorator_match = 100

        # Signature match (function definitions)
        orig_sigs = set(re.findall(r"def\s+(\w+)\s*\([^)]*\)", original))
        gen_sigs = set(re.findall(r"def\s+(\w+)\s*\([^)]*\)", generated))
        if orig_sigs:
            common_sigs = len(orig_sigs & gen_sigs)
            metrics.signature_match = (common_sigs / len(orig_sigs)) * 100
        else:
            metrics.signature_match = 100

        # Intent score (average of semantic metrics)
        metrics.intent_score = (
            metrics.naming_similarity
            + metrics.docstring_present
            + metrics.type_hints_present
            + metrics.decorator_match
            + metrics.signature_match
        ) / 5

        return metrics

    def _compute_format_metrics(
        self,
        original: str,
        generated: str,
        spec: str,
        format_name: str,
    ) -> FormatMetrics:
        """Compute format efficiency metrics."""
        metrics = FormatMetrics(format_name=format_name)

        metrics.spec_chars = len(spec)
        metrics.spec_lines = len(spec.split("\n"))
        metrics.spec_tokens = len(spec) // 4  # Rough estimate

        metrics.original_chars = len(original)
        metrics.generated_chars = len(generated)

        # Compression ratio (how much smaller is spec vs original)
        if metrics.spec_chars > 0:
            metrics.compression_ratio = metrics.original_chars / metrics.spec_chars

        # Expansion ratio (how much generated expanded from spec)
        if metrics.spec_chars > 0:
            metrics.expansion_ratio = metrics.generated_chars / metrics.spec_chars

        # Efficiency score (quality per compression)
        # Higher is better: good reproduction with small spec
        similarity = difflib.SequenceMatcher(None, original, generated).ratio()
        if metrics.compression_ratio > 0:
            metrics.efficiency_score = similarity / (1 / metrics.compression_ratio)

        # Token cost estimate (assuming $0.01 per 1000 tokens for input)
        metrics.token_cost_estimate = (metrics.spec_tokens / 1000) * 0.01

        return metrics

    def _compute_overall_score(self, result: ReproductionResult) -> float:
        """Compute weighted overall score."""
        # Weights for different metric categories
        weights = {
            "text": 0.3,
            "structural": 0.35,
            "semantic": 0.35,
        }

        text_score = (
            result.text.char_similarity * 0.2
            + result.text.line_similarity * 0.3
            + result.text.jaccard_similarity * 0.25
            + result.text.cosine_similarity * 0.25
        )

        structural_score = (
            result.structural.structural_score * 0.6
            + result.structural.element_coverage * 0.4
        )

        semantic_score = result.semantic.intent_score

        overall = (
            text_score * weights["text"]
            + structural_score * weights["structural"]
            + semantic_score * weights["semantic"]
        )

        return overall

    def _get_grade(self, score: float) -> str:
        """Get letter grade from score."""
        if score >= 80:
            return "A"
        elif score >= 65:
            return "B"
        elif score >= 50:
            return "C"
        elif score >= 35:
            return "D"
        else:
            return "F"

    def _generate_recommendations(self, result: ReproductionResult) -> List[str]:
        """Generate improvement recommendations."""
        recs = []

        if result.structural.structural_score < 50:
            recs.append(
                "Improve structural matching - ensure all classes and functions are captured"
            )

        if result.semantic.naming_similarity < 60:
            recs.append(
                "Improve identifier naming - use more descriptive names in specification"
            )

        if result.semantic.type_hints_present < 50:
            recs.append("Add type hints to specification for better type preservation")

        if result.semantic.docstring_present < 50:
            recs.append("Include docstrings in specification for better documentation")

        if result.text.jaccard_similarity < 40:
            recs.append(
                "Improve vocabulary coverage - specification may be missing key terms"
            )

        if result.format.compression_ratio > 5:
            recs.append(
                "High compression - consider adding more detail to specification"
            )

        if result.format.efficiency_score < 0.3:
            recs.append("Low efficiency - try different format or add more structure")

        if not recs:
            recs.append("Good reproduction quality - no major improvements needed")

        return recs


def analyze_reproduction(
    original: str,
    generated: str,
    spec: str = "",
    format_name: str = "",
    verbose: bool = False,
) -> ReproductionResult:
    """Convenience function for reproduction analysis.

    Args:
        original: Original source code
        generated: Generated code
        spec: Specification used
        format_name: Format name
        verbose: Enable verbose logging

    Returns:
        ReproductionResult
    """
    metrics = ReproductionMetrics(verbose=verbose)
    return metrics.analyze(original, generated, spec, format_name)


def compare_formats(
    original: str,
    results: Dict[str, Tuple[str, str]],  # format -> (spec, generated)
    verbose: bool = False,
) -> Dict[str, Any]:
    """Compare reproduction quality across formats.

    Args:
        original: Original source code
        results: Dict mapping format name to (spec, generated) tuple
        verbose: Enable verbose logging

    Returns:
        Comparison results
    """
    metrics = ReproductionMetrics(verbose=verbose)

    comparisons = {}
    for format_name, (spec, generated) in results.items():
        result = metrics.analyze(original, generated, spec, format_name)
        comparisons[format_name] = result

    # Find best format for each metric category
    best = {
        "overall": max(comparisons.items(), key=lambda x: x[1].overall_score),
        "text": max(comparisons.items(), key=lambda x: x[1].text.char_similarity),
        "structural": max(
            comparisons.items(), key=lambda x: x[1].structural.structural_score
        ),
        "semantic": max(comparisons.items(), key=lambda x: x[1].semantic.intent_score),
        "efficiency": max(
            comparisons.items(), key=lambda x: x[1].format.efficiency_score
        ),
    }

    return {
        "results": {k: v.to_dict() for k, v in comparisons.items()},
        "best": {k: v[0] for k, v in best.items()},
        "summary": {
            format_name: {
                "overall": r.overall_score,
                "grade": r.quality_grade,
                "text": r.text.char_similarity,
                "structural": r.structural.structural_score,
                "semantic": r.semantic.intent_score,
            }
            for format_name, r in comparisons.items()
        },
    }
