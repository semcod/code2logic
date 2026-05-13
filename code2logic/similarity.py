"""
Similarity detector using Rapidfuzz.

Detects similar functions across modules to identify
potential duplicates and refactoring opportunities.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List

from .models import ModuleInfo

log = logging.getLogger(__name__)

# Optional Rapidfuzz import
RAPIDFUZZ_AVAILABLE = False
try:
    from rapidfuzz import fuzz, process

    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    fuzz = None
    process = None


class SimilarityDetector:
    """
    Detects similar functions using fuzzy string matching.

    Uses Rapidfuzz for fast similarity computation to identify:
    - Duplicate functions across modules
    - Refactoring opportunities (similar code patterns)
    - Naming inconsistencies

    Example:
        >>> detector = SimilarityDetector(threshold=80.0)
        >>> similar = detector.find_similar_functions(modules)
        >>> for func, matches in similar.items():
        ...     print(f"{func} is similar to: {matches}")
    """

    def __init__(self, threshold: float = 80.0):
        """
        Initialize the similarity detector.

        Args:
            threshold: Minimum similarity score (0-100) to consider as similar
        """
        self.threshold = threshold
        self.max_functions = 8000
        self.progress_every = 250

    def find_similar_functions(self, modules: List[ModuleInfo]) -> Dict[str, List[str]]:
        """
        Find similar functions across all modules.

        Args:
            modules: List of ModuleInfo objects

        Returns:
            Dict mapping function full name to list of similar functions
            with similarity scores
        """
        if not RAPIDFUZZ_AVAILABLE:
            return {}

        start = time.time()

        # Collect all functions
        all_funcs: List[dict] = []
        for m in modules:
            for f in m.functions:
                all_funcs.append({"name": f.name, "full": f"{m.path}::{f.name}"})
            for c in m.classes:
                for method in c.methods:
                    all_funcs.append(
                        {
                            "name": method.name,
                            "full": f"{m.path}::{c.name}.{method.name}",
                        }
                    )

        if len(all_funcs) < 2:
            return {}

        if len(all_funcs) > self.max_functions:
            log.warning(
                "Skipping similarity detection: too many functions (%d > %d). Use --no-similarity to silence this.",
                len(all_funcs),
                self.max_functions,
            )
            return {}

        # Find similar functions
        similar: Dict[str, List[str]] = {}
        names = [f["name"] for f in all_funcs]

        name_to_fulls: Dict[str, List[str]] = defaultdict(list)
        for f in all_funcs:
            name_to_fulls[f["name"]].append(f["full"])

        for i, func in enumerate(all_funcs):
            # Skip common names that would produce false positives
            if func["name"] in ("__init__", "constructor", "toString", "valueOf"):
                continue

            if i > 0 and (i % self.progress_every) == 0:
                log.debug(
                    "Similarity progress: %d/%d (%.2fs)",
                    i,
                    len(all_funcs),
                    time.time() - start,
                )

            matches = process.extract(
                func["name"], names[:i] + names[i + 1 :], scorer=fuzz.ratio, limit=3
            )

            sim_list = []
            for match_name, score, _ in matches:
                if score >= self.threshold and match_name != func["name"]:
                    for full in name_to_fulls.get(match_name, [])[:3]:
                        sim_list.append(f"{full} ({score}%)")

            if sim_list:
                similar[func["full"]] = sim_list

        log.debug(
            "Similarity finished: funcs=%d matches=%d time=%.2fs",
            len(all_funcs),
            len(similar),
            time.time() - start,
        )
        return similar

    def find_duplicate_signatures(
        self, modules: List[ModuleInfo]
    ) -> Dict[str, List[str]]:
        """
        Find functions with identical signatures.

        Args:
            modules: List of ModuleInfo objects

        Returns:
            Dict mapping signature to list of function full names
        """
        signatures: Dict[str, List[str]] = {}

        for m in modules:
            for f in m.functions:
                sig = self._build_signature(f.name, f.params, f.return_type)
                full_name = f"{m.path}::{f.name}"

                if sig in signatures:
                    signatures[sig].append(full_name)
                else:
                    signatures[sig] = [full_name]

            for c in m.classes:
                for method in c.methods:
                    sig = self._build_signature(
                        method.name, method.params, method.return_type
                    )
                    full_name = f"{m.path}::{c.name}.{method.name}"

                    if sig in signatures:
                        signatures[sig].append(full_name)
                    else:
                        signatures[sig] = [full_name]

        # Filter to only duplicates
        return {sig: funcs for sig, funcs in signatures.items() if len(funcs) > 1}

    def _build_signature(
        self, name: str, params: List[str], return_type: str = None
    ) -> str:
        """Build a normalized signature string."""
        # Normalize parameter names
        normalized_params = []
        for p in params[:4]:
            # Extract just the type if available
            if ":" in p:
                _, type_part = p.split(":", 1)
                normalized_params.append(type_part.strip())
            else:
                normalized_params.append("any")

        params_str = ", ".join(normalized_params)
        ret = return_type or "void"

        return f"{name}({params_str}) -> {ret}"


def is_rapidfuzz_available() -> bool:
    """Check if Rapidfuzz is available."""
    return RAPIDFUZZ_AVAILABLE


def get_refactoring_suggestions(
    similar_functions: Dict[str, List[str]],
) -> List[Dict[str, any]]:
    """
    Generate refactoring suggestions based on similar functions.

    Args:
        similar_functions: Dict from find_similar_functions or find_duplicate_signatures

    Returns:
        List of refactoring suggestions with type, functions, and recommendation
    """
    suggestions = []

    # Group by function name pattern
    name_groups: Dict[str, List[str]] = {}
    for func_full, matches in similar_functions.items():
        # Extract function name
        if "::" in func_full:
            _, func_part = func_full.rsplit("::", 1)
            if "." in func_part:
                func_name = func_part.split(".")[-1]
            else:
                func_name = func_part
        else:
            func_name = func_full

        if func_name not in name_groups:
            name_groups[func_name] = []
        name_groups[func_name].append(func_full)
        for match in matches:
            # Remove score suffix
            match_clean = match.split(" (")[0] if " (" in match else match
            if match_clean not in name_groups[func_name]:
                name_groups[func_name].append(match_clean)

    for func_name, locations in name_groups.items():
        if len(locations) < 2:
            continue

        # Determine suggestion type
        classes = set()
        modules = set()
        for loc in locations:
            if "::" in loc:
                mod, rest = loc.rsplit("::", 1)
                modules.add(mod)
                if "." in rest:
                    cls_name = rest.split(".")[0]
                    classes.add(cls_name)

        suggestion = {
            "function": func_name,
            "locations": locations,
            "count": len(locations),
        }

        if len(classes) > 1:
            suggestion["type"] = "extract_to_base_class"
            suggestion["recommendation"] = (
                f"Extract '{func_name}' to a shared base class or mixin"
            )
        elif len(modules) > 1:
            suggestion["type"] = "extract_to_utility"
            suggestion["recommendation"] = (
                f"Extract '{func_name}' to a shared utility module"
            )
        else:
            suggestion["type"] = "consolidate"
            suggestion["recommendation"] = (
                f"Consider consolidating duplicate '{func_name}' implementations"
            )

        suggestions.append(suggestion)

    # Sort by count (most duplicates first)
    suggestions.sort(key=lambda x: -x["count"])

    return suggestions
