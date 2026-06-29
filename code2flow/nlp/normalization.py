"""Query normalization (pipeline steps 1a-1e)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from code2flow.nlp.config import NormalizationConfig

STOPWORDS: dict[str, set[str]] = {
    "en": {
        "the", "is", "a", "an", "of", "to", "for", "and", "or", "in", "on",
        "at", "this", "that", "it", "with", "as", "be", "are", "was", "were",
    },
    "pl": {
        "i", "w", "we", "na", "do", "z", "ze", "że", "to", "jest", "są",
        "się", "o", "po", "za", "od", "the",
    },
}


@dataclass
class NormalizationResult:
    normalized: str = ""
    original: str = ""
    tokens: list[str] | None = None
    language: str = "en"
    steps_applied: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = self.normalized.split()


class QueryNormalizer:
    """Applies a configurable sequence of normalization steps to a query."""

    def __init__(self, config: NormalizationConfig | None = None) -> None:
        self.config = config or NormalizationConfig()

    def normalize(self, query: str, language: str = "en") -> NormalizationResult:
        steps: list[str] = []
        text = query or ""

        if self.config.unicode_nfkc:
            text = unicodedata.normalize("NFKC", text)
            steps.append("unicode_nfkc")

        if self.config.lowercase:
            text = text.lower()
            steps.append("lowercase")

        if self.config.remove_punctuation:
            # Replace any non-word / non-space char with a space. ``\w`` is
            # Unicode-aware so accented and Polish letters are preserved.
            text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
            steps.append("remove_punctuation")

        if self.config.normalize_whitespace:
            text = re.sub(r"\s+", " ", text).strip()
            steps.append("normalize_whitespace")

        tokens = text.split()

        if self.config.remove_stopwords:
            stop = STOPWORDS.get(language, set())
            tokens = [t for t in tokens if t not in stop]
            text = " ".join(tokens)
            steps.append("remove_stopwords")

        return NormalizationResult(
            normalized=text,
            original=query,
            tokens=tokens,
            language=language,
            steps_applied=steps,
        )
