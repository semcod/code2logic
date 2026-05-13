from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    name: str = ""
    entity_type: str = "unknown"
    score: float = 0.0
    metadata: dict | None = None


@dataclass
class EntityResolutionResult:
    entities: list[Entity] = field(default_factory=list)
    resolved: list[Any] = field(default_factory=list)
    query: str = ""

    def get_entities(self) -> list[Entity]:
        return self.entities
