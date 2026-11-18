"""Change detection: grey 64-px-wide thumbnails and their mean absolute difference (0-255)."""
import numpy as np
from PIL import Image

WIDTH = 64


def gray_thumb(img: Image.Image, width: int = WIDTH) -> np.ndarray:
    g = img.convert("L")  # ITU-R 601 luma, same weights as the Android port
    h = max(1, round(width * g.height / max(1, g.width)))
    return np.asarray(g.resize((width, h), Image.BOX), dtype=np.float32)


def diff(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Mean |a - b|; with `mask` only where it is True (all ignored -> 0.0, i.e. "no change")."""
    if a.shape != b.shape:
        return float("inf")
    d = np.abs(a - b)
    if mask is not None and mask.shape == d.shape:
        return float(d[mask].mean()) if mask.any() else 0.0
    return float(np.mean(d))
