# Backward-compat shim: code2flow.nlp stubs
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from code2flow.nlp.normalization import NormalizationResult  # noqa: F401
from code2flow.nlp.intent_matching import IntentMatchingResult, IntentMatch  # noqa: F401
from code2flow.nlp.entity_resolution import EntityResolutionResult, Entity  # noqa: F401


@dataclass
class NLPResult:
    normalized_query: str = ""
    fallback_used: bool = False
    overall_confidence: float = 1.0
    _intent: str = "generic_search"

    def get_intent(self) -> str:
        return self._intent


class NLPConfig:
    pass


FAST_NLP_CONFIG = NLPConfig()
PRECISE_NLP_CONFIG = NLPConfig()


class QueryNormalizer:
    def normalize(self, query: str) -> NormalizationResult:
        return NormalizationResult(normalized=query.lower().strip(), original=query)


class IntentMatcher:
    def match(self, query: str) -> IntentMatchingResult:
        return IntentMatchingResult(
            intent="find_function",
            matches=[IntentMatch(intent="find_function", score=0.8)],
        )


class NLPPipeline:
    def __init__(self, config: NLPConfig | None = None) -> None:
        self.config = config

    def process(self, query: str, language: str = "en") -> NLPResult:
        q = query.strip()
        fallback = not q or len(q) < 3 or all(not c.isalpha() for c in q)
        confidence = 0.3 if fallback else 0.8
        intent = "generic_search" if fallback else "find_function"
        return NLPResult(
            normalized_query=q[:500],
            fallback_used=fallback,
            overall_confidence=confidence,
            _intent=intent,
        )


class EntityResolver:
    def __init__(self) -> None:
        self._entities: list[Any] = []

    def load_from_analysis(self, analysis: Any) -> None:
        pass

    def resolve(self, query: str) -> list[Any]:
        return []
