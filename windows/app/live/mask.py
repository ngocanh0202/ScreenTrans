"""Ignore regions (blinking arrow, animated HUD) are left out of the Live change detection."""
import numpy as np


def ignore_mask(region_px: tuple[int, int, int, int], ignore_px: list[tuple[int, int, int, int]],
                thumb_w: int, thumb_h: int) -> np.ndarray:
    """Boolean (thumb_h, thumb_w) array, True where a thumbnail pixel is compared (not ignored)."""
    keep = np.ones((thumb_h, thumb_w), dtype=bool)
    rx, ry, rw, rh = region_px
    if rw <= 0 or rh <= 0:
        return keep
    for ix, iy, iw, ih in ignore_px:
        x0 = int(np.floor((ix - rx) * thumb_w / rw))
        y0 = int(np.floor((iy - ry) * thumb_h / rh))
        x1 = int(np.ceil((ix + iw - rx) * thumb_w / rw))
        y1 = int(np.ceil((iy + ih - ry) * thumb_h / rh))
        keep[max(0, y0):max(0, min(thumb_h, y1)), max(0, x0):max(0, min(thumb_w, x1))] = False
    return keep
