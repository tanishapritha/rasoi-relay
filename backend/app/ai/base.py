from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Intent:
    name: str
    confidence: float
    needs_clarification: bool = False
    clarification: str | None = None


class IntentProvider(Protocol):
    def classify(self, message: str) -> Intent | None:
        """Return a structured intent, or None when the provider cannot classify safely."""
        ...
