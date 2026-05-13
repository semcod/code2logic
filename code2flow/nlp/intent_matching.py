from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class IntentMatch:
    intent: str = "generic_search"
    score: float = 0.0
    metadata: dict | None = None


@dataclass
class IntentMatchingResult:
    intent: str = "generic_search"
    matches: list[IntentMatch] = field(default_factory=list)
    confidence: float = 0.0

    def get_top_intent(self) -> str:
        return self.intent
