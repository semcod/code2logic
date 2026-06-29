"""Entity resolution (pipeline steps 3a-3e)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from code2flow.nlp.config import EntityResolutionConfig


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text or "", flags=re.UNICODE) if t]


@dataclass
class Entity:
    name: str = ""
    qualified_name: str = ""
    entity_type: str = "unknown"
    confidence: float = 1.0
    aliases: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:  # backward-compat alias
        return self.confidence


@dataclass
class EntityResolutionResult:
    entities: list[Entity] = field(default_factory=list)
    resolved: list[Any] = field(default_factory=list)
    query: str = ""

    def get_entities(self) -> list[Entity]:
        return self.entities


class EntityResolver:
    """Resolves entity references in a query against known codebase entities."""

    def __init__(
        self,
        config: EntityResolutionConfig | dict | None = None,
        codebase_entities: dict[str, list[Entity]] | None = None,
    ) -> None:
        # Support EntityResolver(codebase_entities={...}) positional/keyword.
        if isinstance(config, dict) and codebase_entities is None:
            codebase_entities = config
            config = None
        self.config = config or EntityResolutionConfig()
        self.codebase_entities: dict[str, list[Entity]] = codebase_entities or {}

    def load_from_analysis(self, analysis: Any) -> None:
        """Populate codebase entities from an analysis result."""
        entities: dict[str, list[Entity]] = {}

        def _add(kind: str, items: Any) -> None:
            if not items:
                return
            iterable = items.values() if hasattr(items, "values") else items
            for item in iterable:
                name = getattr(item, "name", None) or str(item)
                qname = getattr(item, "qualified_name", None) or name
                entities.setdefault(kind, []).append(
                    Entity(name=name, qualified_name=qname, entity_type=kind)
                )

        _add("function", getattr(analysis, "functions", None))
        _add("class", getattr(analysis, "classes", None))

        # Fall back to iterating modules if the result is module-structured.
        for module in getattr(analysis, "modules", []) or []:
            _add("function", getattr(module, "functions", None))
            _add("class", getattr(module, "classes", None))

        self.codebase_entities = entities

    def resolve(self, query: str, context: str | None = None) -> EntityResolutionResult:
        threshold = self.config.name_match_threshold
        tokens = _tokenize(query)
        ctx = (context or "").lower()

        results: list[Entity] = []
        for entities in self.codebase_entities.values():
            for entity in entities:
                candidates = [entity.name]
                if self.config.hierarchical_resolution and "." in entity.qualified_name:
                    candidates.append(entity.qualified_name.split(".")[-1])

                best = 0.0
                for tok in tokens:
                    for cand in candidates:
                        best = max(best, _ratio(tok.lower(), cand.lower()))

                if best < threshold:
                    continue

                confidence = best
                if ctx and entity.name.lower() in ctx:
                    confidence = min(1.0, confidence + 0.2)

                aliases: list[str] = []
                if self.config.alias_resolution:
                    short = entity.qualified_name.split(".")[-1]
                    aliases = [
                        a
                        for a in dict.fromkeys([entity.qualified_name, short])
                        if a and a != entity.name
                    ]

                results.append(
                    Entity(
                        name=entity.name,
                        qualified_name=entity.qualified_name,
                        entity_type=entity.entity_type,
                        confidence=round(confidence, 4),
                        aliases=aliases,
                    )
                )

        results.sort(key=lambda e: e.confidence, reverse=True)
        return EntityResolutionResult(entities=results, resolved=results, query=query)
