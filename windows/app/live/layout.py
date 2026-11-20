"""Live translation box layout (rules: shared/fixtures/live_layout; the Kotlin Layout.kt passes the same files)."""
from typing import Callable

WIDEN_SHARE = 0.25   # a box may grow this much of its width...
WIDEN_EMS = 4        # ...or this many font sizes (a short source: "Hello" -> "Xin chào"), whichever is more


def widen(width: int, lines: Callable[[int], int], room: int, px: float) -> int:
    """Box width for a translation: the source width, or the smallest wider one (up to the cap) that needs as few
    lines as the cap does. Vietnamese runs longer than English: a short source dropped its last word to a new line."""
    cap = min(room, width + max(int(WIDEN_SHARE * width), int(WIDEN_EMS * px)))
    if cap <= width:
        return width
    target = lines(cap)
    if lines(width) <= target:
        return width
    lo, hi = width, cap  # lines(lo) > target, lines(hi) == target
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if lines(mid) <= target:
            hi = mid
        else:
            lo = mid
    return hi


def separate(rects: list[tuple], gap: int = 2) -> list[tuple]:
    """Boxes (left, top, right, bottom) moved down until none covers another, upper ones first; input order kept.
    A translation taller than its source used to cover the next block's translation."""
    order = sorted(range(len(rects)), key=lambda i: (rects[i][1], rects[i][0]))
    placed: list[tuple] = []
    out: list[tuple] = list(rects)
    for i in order:
        l, t, r, b = rects[i]
        moved = True
        while moved:
            moved = False
            for pl, pt, pr, pb in placed:
                if l < pr and r > pl and t < pb and b > pt:
                    t, b = pb + gap, pb + gap + (b - t)
                    moved = True
        out[i] = (l, t, r, b)
        placed.append(out[i])
    return out
