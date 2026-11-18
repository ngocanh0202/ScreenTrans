"""Live state machine: when to OCR a watched region and whether to translate the result.

Rules are specified in shared/fixtures/live/README.md; the Kotlin port passes the same fixtures.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Literal


@dataclass
class LiveParams:
    interval_ms: int = 300
    active_interval_ms: int = 100
    settle_ms: int = 250
    max_wait_ms: int = 2000
    change_threshold: float = 5.0
    partial_interval_ms: int = 0  # > 0: OCR while the text is still typing (Live realtime sentence by sentence)


class Action(Enum):
    WAIT = "wait"
    OCR = "ocr"
    PARTIAL = "partial"


def _norm(text: str) -> str:
    return " ".join(text.split())


class LiveMachine:
    def __init__(self, params: LiveParams | None = None):
        self.p = params or LiveParams()
        self.state: Literal["idle", "changing"] = "idle"
        self._changed_at = 0
        self._last_change = 0
        self._reason: Literal["settled", "max_wait"] = "settled"
        self._last_ocr = ""
        self._last_translated = ""
        self._suppress_next = False
        self._last_partial = 0

    @property
    def final(self) -> bool:
        """The last OCR came from the text standing still (not from max_wait): every sentence is done."""
        return self._reason == "settled"

    def next_delay_ms(self) -> int:
        return self.p.active_interval_ms if self.state == "changing" else self.p.interval_ms

    def on_overlay_changed(self) -> None:
        """Our own overlay was redrawn: the next frame is only a new reference."""
        self._suppress_next = True

    def on_frame(self, now_ms: int, diff: float) -> Action:
        if self._suppress_next:
            self._suppress_next = False
            return Action.WAIT
        changed = diff > self.p.change_threshold
        if self.state == "idle":
            if changed:
                self.state = "changing"
                self._changed_at = self._last_change = self._last_partial = now_ms
            return Action.WAIT
        if changed:
            self._last_change = now_ms
        if now_ms - self._last_change >= self.p.settle_ms:
            self.state, self._reason = "idle", "settled"
            return Action.OCR
        if now_ms - self._changed_at >= self.p.max_wait_ms:
            self.state, self._reason = "idle", "max_wait"
            return Action.OCR
        if self.p.partial_interval_ms > 0 and now_ms - self._last_partial >= self.p.partial_interval_ms:
            self._last_partial = now_ms
            return Action.PARTIAL
        return Action.WAIT

    def forget_translation(self) -> None:
        """The last translation never reached the screen (superseded / failed): allow it again."""
        self._last_translated = ""

    def on_text(self, now_ms: int, text: str) -> Literal["translate", "skip", "wait"]:
        t = _norm(text)
        if not t:
            self._last_ocr = ""
            return "skip"
        if t == self._last_translated:
            self._last_ocr = t
            return "skip"
        if self._reason == "max_wait" and t != self._last_ocr:
            # The text may still be typing: keep watching, translate once it settles or repeats.
            self._last_ocr = t
            self.state = "changing"
            self._changed_at = now_ms
            return "wait"
        self._last_ocr = self._last_translated = t
        return "translate"
