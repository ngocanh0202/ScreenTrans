"""Live realtime: which sentences of a text block are finished (rules: shared/fixtures/live_sentences)."""
import re

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
                and previous[-1].strip() == last):
            return n
        return n - 1
