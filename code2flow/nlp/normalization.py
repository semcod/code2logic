from __future__ import annotations
from dataclasses import dataclass


@dataclass
class NormalizationResult:
    normalized: str = ""
    original: str = ""
    tokens: list[str] | None = None
    language: str = "en"

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = self.normalized.split()
