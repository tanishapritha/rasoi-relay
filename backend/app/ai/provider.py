from app.ai.base import Intent, IntentProvider
from app.ai.intent_parser import parse_intent


class DeterministicIntentProvider:
    """No-credential fallback used in local development and automated tests."""

    def classify(self, message: str) -> Intent:
        return parse_intent(message)


def get_intent_provider() -> IntentProvider:
    # Hosted model providers can be added behind this interface without changing services.
    # The deterministic provider is the only implemented provider at this stage.
    return DeterministicIntentProvider()
