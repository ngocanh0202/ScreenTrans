"""Live: leave OCR noise and UI labels out before translating (rules: shared/fixtures/live_filter)."""
import re

from app.text.postprocess import Paragraph

_END = re.compile(r"[.!?…][\"'”’)]*$")


def worth_translating(p: Paragraph) -> bool:
    if p.kind == "name":
        return True
    text = p.text.strip()
    chars = [c for c in text if not c.isspace()]
    letters = [c for c in chars if c.isalpha()]
    ended = bool(_END.search(text))  # "Hi.", "No!" are real (short) lines of dialogue
    if len(letters) < (2 if ended else 3) or len(letters) < 0.5 * len(chars):
        return False
    words = text.split()
    if any(any(c.isalpha() for c in w) and any(c.isdigit() for c in w) for w in words):
        return False  # "St3loo": OCR noise
    if len(words) <= 2 and any(w.strip(".,:;!?").isdigit() for w in words):
        return False  # "Level 23": a number label
    if len(words) == 1 and not ended:
        return False  # "AUTO", "SKIP": UI labels
    if not any(sum(c.isalpha() for c in w) >= 2 for w in words):
        return False  # "X X X"
    line = getattr(p, "line_height", 0.0)
    if line > 0 and (p.right - p.left) < 3 * line:
        return False  # narrower than three line heights: vertical text / noise
    return True
