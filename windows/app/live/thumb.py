"""Change detection: grey 160-px-wide thumbnails; a change = how many thumbnail cells changed clearly.

A mean over the whole thumbnail hid small changes (a new dialogue line on a full screen moved it by < 1),
so Live only ever read the first line. Counting cells that changed by more than CELL_DELTA grey levels
sees one short word anywhere while ignoring capture noise and slight brightness flicker.
"""
import numpy as np
from PIL import Image

WIDTH = 160
CELL_DELTA = 16.0  # a cell changed when its grey level moved by more than this (0-255)


def gray_thumb(img: Image.Image, width: int = WIDTH) -> np.ndarray:
    g = img.convert("L")  # ITU-R 601 luma, same weights as the Android port
    w = min(width, g.width)  # never upscaled
    h = max(1, round(w * g.height / max(1, g.width)))
    return np.asarray(g.resize((w, h), Image.BOX), dtype=np.float32)


def diff(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Number of cells whose grey level changed by more than CELL_DELTA; with `mask` only where it is True.
    Different sizes -> inf (always a change)."""
    if a.shape != b.shape:
        return float("inf")
    changed = np.abs(a - b) > CELL_DELTA
    if mask is not None and mask.shape == changed.shape:
        changed &= mask
    return float(np.count_nonzero(changed))
