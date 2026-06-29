"""Intent matching (pipeline steps 2a-2e) with multilingual fuzzy matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from code2flow.nlp.config import IntentMatchingConfig

# Intent registry. ``nouns`` are the discriminating keywords that determine the
# intent; ``verbs`` are shared action words that only weakly hint at an intent.
# Both English and Polish keywords are listed so the same intent resolves across
# languages.
INTENT_DEFINITIONS: dict[str, dict[str, list[str]]] = {
    "find_function": {
        "nouns": [
            "function", "functions", "func", "method", "methods",
            "funkcja", "funkcję", "funkcji", "funkcje", "metoda", "metodę",
        ],
        "verbs": ["find", "search", "show", "get", "locate", "znajdź", "szukaj", "pokaż"],
    },
    "find_class": {
        "nouns": ["class", "classes", "klasa", "klasę", "klasy", "klas"],
        "verbs": ["find", "search", "show", "get", "znajdź", "szukaj", "pokaż"],
    },
    "call_graph": {
        "nouns": [
            "call", "calls", "graph", "callgraph", "caller", "callers",
            "graf", "wywołań", "wywołania", "wywołanie",
        ],
        "verbs": ["show", "display", "draw", "pokaż", "wyświetl"],
    },
    "analyze_flow": {
        "nouns": [
            "flow", "dataflow", "controlflow", "przepływ", "przepływu",
        ],
        "verbs": ["analyze", "analyse", "trace", "analizuj", "prześledź"],
    },
    "explain_code": {
        "nouns": ["code", "explanation", "kod", "kodu"],
        "verbs": ["explain", "describe", "wyjaśnij", "opisz"],
    },
}


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text.lower(), flags=re.UNICODE) if t]


@dataclass
class IntentMatch:
    intent: str = "generic_search"
    confidence: float = 0.0
    score: float = 0.0
    keyword_score: float = 0.0
    context_score: float = 0.0
    metadata: dict | None = None


@dataclass
class IntentMatchingResult:
    intent: str = "generic_search"
    matches: list[IntentMatch] = field(default_factory=list)
    all_matches: list[IntentMatch] = field(default_factory=list)
    primary_intent: IntentMatch | None = None
    confidence: float = 0.0
    strategy_used: str = "best_match"

    def get_top_intent(self) -> str:
        return self.intent


class IntentMatcher:
    """Matches a normalized query against the known intent registry."""

    def __init__(self, config: IntentMatchingConfig | None = None) -> None:
        self.config = config or IntentMatchingConfig()

    def _best_match(self, tokens: list[str], keywords: list[str]) -> float:
        best = 0.0
        for kw in keywords:
            for tok in tokens:
                r = _ratio(tok, kw)
                if r > best:
                    best = r
        return best

    def match(self, query: str, context=None) -> IntentMatchingResult:
        threshold = self.config.fuzzy_threshold
        tokens = _tokenize(query)

        ctx_tokens: list[str] = []
        if context:
            if isinstance(context, str):
                context = [context]
            for item in context:
                ctx_tokens.extend(_tokenize(str(item)))

        matches: list[IntentMatch] = []
        for intent, definition in INTENT_DEFINITIONS.items():
            noun_best = self._best_match(tokens, definition["nouns"])
            verb_best = self._best_match(tokens, definition["verbs"])

            noun_score = noun_best if noun_best >= threshold else 0.0
            verb_score = verb_best if verb_best >= threshold else 0.0

            ctx_noun = self._best_match(ctx_tokens, definition["nouns"])
            context_score = ctx_noun if ctx_noun >= threshold else 0.0

            # Nouns dominate; verbs are shared action words with low weight.
            keyword_score = noun_score if noun_score > 0 else verb_score * 0.3
            confidence = noun_score if noun_score > 0 else verb_score

            rank = (
                keyword_score * self.config.keyword_weight
                + context_score * self.config.context_weight
            )

            if rank > 0 or context_score > 0:
                matches.append(
                    IntentMatch(
                        intent=intent,
                        confidence=round(confidence, 4),
                        score=round(rank, 4),
                        keyword_score=round(keyword_score, 4),
                        context_score=round(context_score, 4),
                    )
                )

        matches.sort(key=lambda m: m.score, reverse=True)
        primary = matches[0] if matches else None

        return IntentMatchingResult(
            intent=primary.intent if primary else "generic_search",
            matches=matches,
            all_matches=matches,
            primary_intent=primary,
            confidence=primary.confidence if primary else 0.0,
            strategy_used=self.config.multi_intent_strategy,
        )
