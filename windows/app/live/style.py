"""Live "giống game" style: the translation drawn with the source text's size and colours
(rules: shared/fixtures/live_style; the Kotlin port BlockStyle.kt passes the same files)."""
from dataclasses import dataclass

import numpy as np

BORDER = 2
BORDER_STD_MAX = 24.0   # a busier border is a picture behind the text: no reliable background colour
TEXT_SHARE = 0.15       # the 15% inner pixels farthest from the background are the glyphs
MIN_CONTRAST = 3.0      # WCAG contrast ratio; below it the sampled colours are hard to read
FONT_PER_LINE = 0.8     # font size (px) for an OCR line box height (px)


@dataclass(frozen=True)
class BlockStyle:
    text: tuple[int, int, int]
    bg: tuple[int, int, int]


def _luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(float(v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def sample_style(block: np.ndarray) -> BlockStyle | None:
    """`block`: H x W x 3 RGB pixels of one text block (its OCR box). None -> use the readable style."""
    h, w = block.shape[:2]
    if h < 2 * BORDER + 2 or w < 2 * BORDER + 2:
        return None
    px = block.astype(np.float32)
    ring = np.concatenate([px[:BORDER].reshape(-1, 3), px[-BORDER:].reshape(-1, 3),
                           px[BORDER:-BORDER, :BORDER].reshape(-1, 3), px[BORDER:-BORDER, -BORDER:].reshape(-1, 3)])
    luma = ring @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    if float(luma.std()) > BORDER_STD_MAX:
        return None
    bg = np.median(ring, axis=0)
    inner = px[BORDER:-BORDER, BORDER:-BORDER].reshape(-1, 3)
    dist = np.linalg.norm(inner - bg, axis=1)
    k = max(1, int(len(inner) * TEXT_SHARE))
    text = np.median(inner[np.argsort(dist)[-k:]], axis=0)
    t = tuple(int(round(v)) for v in text)
    b = tuple(int(round(v)) for v in bg)
    if contrast(t, b) < MIN_CONTRAST:
        return None
    return BlockStyle(t, b)


def font_px_for(line_height: float) -> float | None:
    """Font size in pixels matching a source line of `line_height` pixels (None when unknown)."""
    return line_height * FONT_PER_LINE if line_height > 0 else None


FONT_STEADY = 0.30  # a new read whose size differs less than this keeps the old size (OCR line heights jitter)


def steady_font(old: float | None, new: float | None) -> float | None:
    """The size to draw: OCR line heights jitter a few pixels between reads, which made translations shrink and
    grow; only a real change of the source size (> 30 %) is followed."""
    if old is None or new is None:
        return new if old is None else old
    return old if abs(new - old) <= FONT_STEADY * old else new


def steady_box(old: tuple | None, new: tuple) -> tuple:
    """Where to draw (left, top, right, bottom): a read whose top-left is within max(8 px, 0.35 x the line height)
    of the old one keeps the old top-left (OCR boxes jitter, translations jumped up and down) and may only grow
    to the right / down (text still typing); a larger shift is a block that really moved."""
    if old is None or old == (0, 0, 0, 0):
        return new
    tol = max(8.0, 0.35 * (old[3] - old[1]))
    if abs(new[0] - old[0]) > tol or abs(new[1] - old[1]) > tol:
        return new
    return old[0], old[1], max(old[2], new[2]), max(old[3], new[3])


STYLE_CELLS = 6  # Live regions are split into 6 x 6 cells: one remembered "match" style per cell and kind


def style_cell(box: tuple, size: tuple[int, int], kind: str) -> str:
    """Which remembered style a block uses (rules: shared/fixtures/live_style_cells): sampling every new block made
    the colours change all the time (a line read while fading in, or a failed sample between two good ones)."""
    w, h = max(1, size[0]), max(1, size[1])
    col = min(STYLE_CELLS - 1, max(0, int(box[0] * STYLE_CELLS // w)))
    row = min(STYLE_CELLS - 1, max(0, int(box[1] * STYLE_CELLS // h)))
    return f"{kind}:{col}:{row}"
