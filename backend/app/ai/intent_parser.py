from app.ai.base import Intent


UNCERTAIN_PHYSICAL_PHRASES = (
    "yaad nahi", "pata nahi", "not sure", "don't remember", "do not remember",
    "can't remember", "cannot remember", "unsure", "not certain",
)


def parse_intent(message: str) -> Intent:
    text = " ".join(message.casefold().strip().split())
    if not text:
        return Intent("unknown", 0.0, True, "Tell me what you need help with.")
    if any(word in text for word in ("back", "resume", "recover", "kya karna", "next kya", "what next", "continue")):
        return Intent("recover_meal", 0.92)
    if any(word in text for word in ("interrupt", "phone call", "delivery", "left kitchen", "break")):
        return Intent("report_interruption", 0.88)
    if any(word in text for word in ("gas", "stove", "flame", "burner")) and any(phrase in text for phrase in UNCERTAIN_PHYSICAL_PHRASES):
        return Intent("report_uncertain_physical_state", 0.98)
    if any(word in text for word in ("status", "progress", "how far", "kitna hua")):
        return Intent("get_meal_status", 0.85)
    if any(word in text for word in ("delay", "taking longer", "late", "der ho", "15 minutes")):
        return Intent("report_delay", 0.72)
    return Intent("unknown", 0.0, True, "I didn't confidently understand that. Ask for your next step, meal status, or report an interruption.")
