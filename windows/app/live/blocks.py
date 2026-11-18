"""Large-area Live: which text blocks are new, still shown, or gone (rules: shared/fixtures/live_blocks)."""
import itertools
import math
from dataclasses import dataclass, field

from app.text.postprocess import Paragraph


def _norm(text: str) -> str:
    return " ".join(text.split())


@dataclass
class Block:
    key: str
    text: str
    box: tuple[float, float, float, float]  # left, top, right, bottom
    paragraph: Paragraph

    @property
    def center(self) -> tuple[float, float]:
        l, t, r, b = self.box
        return (l + r) / 2, (t + b) / 2


@dataclass
class BlockDiff:
    added: list[Block]
    kept: list[Block]
    removed: list[Block]
    grown: list[Block] = field(default_factory=list)  # same block, text still typing (longer, same top-left)


class BlockTracker:
    def __init__(self, max_blocks: int = 30, near_px: float = 24):
        self.max_blocks = max_blocks
        self.near_px = near_px
        self.shown: list[Block] = []
        self._ids = itertools.count(1)

    def update(self, paragraphs: list[Paragraph]) -> BlockDiff:
        paras = sorted(paragraphs, key=lambda p: (p.top, p.left))[: self.max_blocks]
        free = list(self.shown)
        added, kept, grown, now = [], [], [], []
        for p in paras:
            box = (p.left, p.top, p.right, p.bottom)
            text = _norm(p.text)
            cx, cy = (p.left + p.right) / 2, (p.top + p.bottom) / 2
            match = next((b for b in free if _norm(b.text) == text
                          and math.dist(b.center, (cx, cy)) <= self.near_px), None)
            if match is not None:
                free.remove(match)
                block = Block(match.key, text, box, p)
                kept.append(block)
            elif (base := next((b for b in free if text.startswith(_norm(b.text)) and len(text) > len(_norm(b.text))
                                and math.dist(b.box[:2], box[:2]) <= self.near_px), None)) is not None:
                free.remove(base)
                block = Block(base.key, text, box, p)
                grown.append(block)
            else:
                block = Block(f"b{next(self._ids)}", text, box, p)
                added.append(block)
            now.append(block)
        self.shown = now
        return BlockDiff(added, kept, free, grown)

    def forget(self, keys) -> None:
        """Blocks whose translation never arrived: they count as new on the next update."""
        keys = set(keys)
        self.shown = [b for b in self.shown if b.key not in keys]


class RateLimiter:
    """At most one OCR per min_interval_ms (large-area Live)."""

    def __init__(self, min_interval_ms: int = 1000):
        self.min_interval_ms = min_interval_ms
        self._last: int | None = None

    def allow(self, now_ms: int) -> bool:
        if self._last is not None and now_ms - self._last < self.min_interval_ms:
            return False
        self._last = now_ms
        return True
