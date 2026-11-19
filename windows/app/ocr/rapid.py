"""RapidOCR (PaddleOCR models on onnxruntime): an optional, slower OCR engine for one-shot translations."""
import math

from PIL import Image

from app.ocr.base import Line
from app.ocr.deskew import STRAIGHT_DEG, from_corners


def lines_from_rapid(result) -> list[Line]:
    """RapidOCR detections [(4 points, text, score)] -> lines: tilted boxes keep their angle (deskewed frame);
    straight fragments on one row are joined left to right."""
    straight: list[tuple[float, float, float, float, str]] = []  # top, bottom, left, right, text
    out: list[Line] = []
    for quad, text, _score in result or []:
        pts = [(float(x), float(y)) for x, y in quad]
        angle = math.degrees(math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]))
        if abs(angle) >= STRAIGHT_DEG:
            out.append(Line(text, *from_corners(pts, angle), angle))
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        straight.append((min(ys), max(ys), min(xs), max(xs), text))
    rows: list[list[tuple]] = []
    for frag in sorted(straight):
        centre = (frag[0] + frag[1]) / 2
        if rows and rows[-1][0][0] <= centre <= rows[-1][0][1]:
            rows[-1].append(frag)
        else:
            rows.append([frag])
    for row in rows:
        row.sort(key=lambda f: f[2])
        top, bottom = min(f[0] for f in row), max(f[1] for f in row)
        left, right = min(f[2] for f in row), max(f[3] for f in row)
        out.append(Line(" ".join(f[4] for f in row), left, top, right - left, bottom - top))
    return out


class RapidOcr:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def recognize(self, img: Image.Image) -> list[Line]:
        import numpy as np

        result, _ = self._engine(np.array(img.convert("RGB")))
        return lines_from_rapid(result)
