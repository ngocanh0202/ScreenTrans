"""Change detection: grey 64-px-wide thumbnails and their mean absolute difference (0-255)."""
import numpy as np
from PIL import Image

WIDTH = 64


def gray_thumb(img: Image.Image, width: int = WIDTH) -> np.ndarray:
    g = img.convert("L")  # ITU-R 601 luma, same weights as the Android port
    h = max(1, round(width * g.height / max(1, g.width)))
    return np.asarray(g.resize((width, h), Image.BOX), dtype=np.float32)


def diff(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return float("inf")
    return float(np.mean(np.abs(a - b)))
