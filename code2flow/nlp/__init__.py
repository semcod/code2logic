"""NLP query-processing pipeline for code2flow.

Provides a small, dependency-free NLP pipeline with four stages:

1. Query normalization
2. Intent matching (multilingual fuzzy matching)
3. Entity resolution
4. Orchestration / confidence scoring / output formatting
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from code2flow.nlp.config import (  # noqa: F401
    FAST_NLP_CONFIG,
    PRECISE_NLP_CONFIG,
    EntityResolutionConfig,
    IntentMatchingConfig,
    NLPConfig,
    NormalizationConfig,
)
from code2flow.nlp.entity_resolution import (  # noqa: F401
    Entity,
    EntityResolutionResult,
    EntityResolver,
)
from code2flow.nlp.intent_matching import (  # noqa: F401
    IntentMatch,
    IntentMatcher,
    IntentMatchingResult,
)
from code2flow.nlp.normalization import (  # noqa: F401
    NormalizationResult,
    QueryNormalizer,
)

# Human-readable recommendation per intent.
_ACTION_BY_INTENT = {
    "find_function": "search_functions",
    "find_class": "search_classes",
    "call_graph": "build_call_graph",
    "analyze_flow": "analyze_flow",
    "explain_code": "explain_code",
    "generic_search": "generic_search",
}


@dataclass
class StageResult:
    name: str
    success: bool = True
    confidence: float = 0.0
    data: Any = None


@dataclass
class NLPResult:
    query: str = ""
    normalized_query: str = ""
    language: str = "en"
    stages: list[StageResult] = field(default_factory=list)
    stage_confidences: dict[str, float] = field(default_factory=dict)
    overall_confidence: float = 0.0
    intent: str | None = None
    entities: list[Entity] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str | None = None
    formatted_response: str = ""
    action_recommendation: str = ""

    def get_intent(self) -> str:
        if self.fallback_used or not self.intent:
            return "generic_search"
        return self.intent

    def is_successful(self) -> bool:
        return (
            not self.fallback_used
            and self.intent is not None
            and self.overall_confidence >= 0.5
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "normalized_query": self.normalized_query,
            "language": self.language,
            "intent": self.get_intent(),
            "overall_confidence": self.overall_confidence,
            "stage_confidences": self.stage_confidences,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "entities": [e.name for e in self.entities],
            "formatted_response": self.formatted_response,
            "action_recommendation": self.action_recommendation,
        }


class NLPPipeline:
    """Orchestrates normalization, intent matching and entity resolution."""

    def __init__(
        self,
        config: NLPConfig | None = None,
        codebase_entities: dict[str, list[Entity]] | None = None,
    ) -> None:
        self.config = config or NLPConfig()
        self.normalizer = QueryNormalizer(self.config.normalization)
        self.matcher = IntentMatcher(self.config.intent_matching)
        self.resolver = EntityResolver(self.config.entity_resolution, codebase_entities)

    def process(self, query: str, language: str = "en") -> NLPResult:
        stages: list[StageResult] = []
        confidences: dict[str, float] = {}

        # Stage 1: normalization
        norm = self.normalizer.normalize(query, language=language)
        norm_conf = 1.0 if norm.tokens else 0.0
        stages.append(StageResult("normalization", True, norm_conf, norm))
        confidences["normalization"] = norm_conf

        # Stage 2: intent matching
        intent_res = self.matcher.match(norm.normalized)
        intent_conf = intent_res.confidence
        stages.append(StageResult("intent", True, intent_conf, intent_res))
        confidences["intent"] = intent_conf

        # Stage 3: entity resolution
        entity_res = self.resolver.resolve(norm.normalized)
        entity_conf = max(
            (e.confidence for e in entity_res.entities), default=0.0
        )
        stages.append(StageResult("entity", True, entity_conf, entity_res))
        confidences["entity"] = entity_conf

        overall = round(
            0.5 * intent_conf + 0.3 * entity_conf + 0.2 * norm_conf, 4
        )

        intent = (
            intent_res.primary_intent.intent if intent_res.primary_intent else None
        )

        fallback_used = False
        fallback_reason: str | None = None
        if intent is None:
            fallback_used = True
            fallback_reason = "no_intent_detected"
        elif overall < self.config.fallback_threshold:
            fallback_used = True
            fallback_reason = "low_confidence"

        resolved_intent = intent if intent else "generic_search"
        action = _ACTION_BY_INTENT.get(resolved_intent, "generic_search")
        formatted = (
            f"Detected intent '{resolved_intent}' "
            f"(confidence {overall:.2f}) for query: {norm.normalized!r}"
        )

        return NLPResult(
            query=query,
            normalized_query=norm.normalized,
            language=language,
            stages=stages,
            stage_confidences=confidences,
            overall_confidence=overall,
            intent=intent,
            entities=entity_res.entities,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            formatted_response=formatted,
            action_recommendation=action,
        )


__all__ = [
    "NLPPipeline",
    "NLPResult",
    "StageResult",
    "NLPConfig",
    "NormalizationConfig",
    "IntentMatchingConfig",
    "EntityResolutionConfig",
    "FAST_NLP_CONFIG",
    "PRECISE_NLP_CONFIG",
    "QueryNormalizer",
    "NormalizationResult",
    "IntentMatcher",
    "IntentMatch",
    "IntentMatchingResult",
    "EntityResolver",
    "Entity",
    "EntityResolutionResult",
]
