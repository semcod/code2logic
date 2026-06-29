"""YAML-driven configuration for the NLP processing pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

import yaml


@dataclass
class NormalizationConfig:
    """Configuration for query normalization (steps 1a-1e)."""

    lowercase: bool = True
    remove_punctuation: bool = True
    normalize_whitespace: bool = True
    unicode_nfkc: bool = True
    remove_stopwords: bool = False


@dataclass
class IntentMatchingConfig:
    """Configuration for intent matching (steps 2a-2e)."""

    fuzzy_threshold: float = 0.8
    keyword_weight: float = 1.0
    context_weight: float = 0.5
    context_window: int = 3
    multi_intent_strategy: str = "best_match"


@dataclass
class EntityResolutionConfig:
    """Configuration for entity resolution (steps 3a-3e)."""

    name_match_threshold: float = 0.7
    hierarchical_resolution: bool = False
    alias_resolution: bool = False


@dataclass
class NLPConfig:
    """Top-level NLP pipeline configuration."""

    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    intent_matching: IntentMatchingConfig = field(default_factory=IntentMatchingConfig)
    entity_resolution: EntityResolutionConfig = field(
        default_factory=EntityResolutionConfig
    )
    enable_normalization: bool = True
    enable_intent_matching: bool = True
    enable_entity_resolution: bool = True
    fallback_threshold: float = 0.5
    verbose: bool = False

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "normalization": asdict(self.normalization),
            "intent_matching": asdict(self.intent_matching),
            "entity_resolution": asdict(self.entity_resolution),
            "enable_normalization": self.enable_normalization,
            "enable_intent_matching": self.enable_intent_matching,
            "enable_entity_resolution": self.enable_entity_resolution,
            "fallback_threshold": self.fallback_threshold,
            "verbose": self.verbose,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NLPConfig":
        data = dict(data or {})
        norm = NormalizationConfig(**(data.pop("normalization", {}) or {}))
        intent = IntentMatchingConfig(**(data.pop("intent_matching", {}) or {}))
        entity = EntityResolutionConfig(**(data.pop("entity_resolution", {}) or {}))

        scalar_fields = {
            f.name
            for f in fields(cls)
            if f.name
            not in {"normalization", "intent_matching", "entity_resolution"}
        }
        extra = {k: v for k, v in data.items() if k in scalar_fields}
        return cls(
            normalization=norm,
            intent_matching=intent,
            entity_resolution=entity,
            **extra,
        )

    @classmethod
    def from_yaml(cls, path: str) -> "NLPConfig":
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls.from_dict(data)

    def to_yaml(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self.to_dict(), handle, sort_keys=False, allow_unicode=True)


# Preset configurations -----------------------------------------------------
FAST_NLP_CONFIG = NLPConfig(
    normalization=NormalizationConfig(remove_stopwords=False),
    intent_matching=IntentMatchingConfig(fuzzy_threshold=0.75),
)

PRECISE_NLP_CONFIG = NLPConfig(
    normalization=NormalizationConfig(remove_stopwords=True),
    intent_matching=IntentMatchingConfig(fuzzy_threshold=0.85),
    entity_resolution=EntityResolutionConfig(
        hierarchical_resolution=True, alias_resolution=True
    ),
)
