"""Live realtime: which sentences of a text block are finished (rules: shared/fixtures/live_sentences)."""
import re

_CONFUSABLE = str.maketrans({"i": "l", "1": "l", "|": "l", "0": "o"})


def ocr_key(text: str) -> str:
    """Two reads of the same text on an animated background differ in letters OCR confuses (I/l/1/|, 0/O) or
    in case: the same key. A different length is a real change (text still typing)."""
    return " ".join(text.split()).lower().translate(_CONFUSABLE)


_END = re.compile(r"(?:[.!?]|…)[\"'”’)」』]*$")


class SentenceGate:
    @staticmethod
    def done(sentences: list[str], previous: list[str] | None, final: bool) -> int:
        """Number of leading sentences that are finished and may be translated and shown."""
        n = len(sentences)
        if n == 0 or final:
            return n
        last = sentences[-1].strip()
        if (_END.search(last) and previous is not None and len(previous) == n
                and ocr_key(previous[-1]) == ocr_key(last)):
            return n
        return n - 1
