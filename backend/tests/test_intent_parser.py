from app.ai.intent_parser import parse_intent


def test_hinglish_recovery_intent():
    assert parse_intent("I'm back, kya karna hai ab?").name == "recover_meal"


def test_uncertain_stove_state_requires_confirmation():
    intent = parse_intent("Gas band hai ya nahi, yaad nahi")
    assert intent.name == "report_uncertain_physical_state"


def test_unknown_message_requests_clarification():
    intent = parse_intent("Tell me a joke")
    assert intent.name == "unknown"
    assert intent.needs_clarification is True
