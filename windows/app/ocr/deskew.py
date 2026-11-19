"""Tilted text: OCR lines are expressed in a frame rotated by -angle around the image origin (0, 0), so the
post-processing rules for straight text apply unchanged; overlays rotate back by +angle when drawing.
Angles in degrees, clockwise positive (as ML Kit). |angle| < STRAIGHT_DEG counts as straight.
"""
import math

STRAIGHT_DEG = 2.0
MIN_SPAN_HEIGHTS = 3.0  # word centres must span at least this many word heights to measure a slope


def rotate_point(x: float, y: float, angle: float) -> tuple[float, float]:
    """Screen point -> tilted (straightened) frame."""
    a = math.radians(angle)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def unrotate_point(x: float, y: float, angle: float) -> tuple[float, float]:
    """Tilted frame -> screen point."""
    a = math.radians(angle)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def from_corners(points: list[tuple[float, float]], angle: float) -> tuple[float, float, float, float]:
    """Four corners (clockwise from top-left, screen pixels) of a tilted line -> (left, top, width, height)
    in the tilted frame."""
    cx = sum(p[0] for p in points) / 4
    cy = sum(p[1] for p in points) / 4
    width = math.dist(points[0], points[1])
    height = math.dist(points[1], points[2])
    dcx, dcy = rotate_point(cx, cy, angle)
    return dcx - width / 2, dcy - height / 2, width, height


def from_words(rects: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float, float]:
    """Word boxes (x, y, w, h; axis aligned) of one OCR line -> (angle, left, top, width, height): the angle is
    the slope from the first to the last word centre; a straight line keeps its plain bounding box."""
    left = min(x for x, _, _, _ in rects)
    top = min(y for _, y, _, _ in rects)
    right = max(x + w for x, _, w, _ in rects)
    bottom = max(y + h for _, y, _, h in rects)
    angle = 0.0
    xs = [x + w / 2 for x, _, w, _ in rects]
    ys = [y + h / 2 for _, y, _, h in rects]
    # Trust a slope only over a long enough run of words: a short line of uneven words ("The was") would
    # otherwise look tilted. Least-squares over every word centre.
    if len(rects) >= 2 and max(xs) - min(xs) >= MIN_SPAN_HEIGHTS * max(h for *_, h in rects):
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        angle = math.degrees(math.atan2(sxy, sxx))
    if abs(angle) < STRAIGHT_DEG:
        return 0.0, left, top, right - left, bottom - top
    centres = [rotate_point(x + w / 2, y + h / 2, angle) for x, y, w, h in rects]
    # an axis-aligned word box of a tilted word is a bit too big: shrink it back to the word itself
    c, s = abs(math.cos(math.radians(angle))), abs(math.sin(math.radians(angle)))
    sizes = [((w * c - h * s) / (c * c - s * s), (h * c - w * s) / (c * c - s * s)) if c * c - s * s > 0.2 else (w, h)
             for _, _, w, h in rects]
    sizes = [(max(sw, 1.0), max(sh, 1.0)) for sw, sh in sizes]
    l = min(cx - sw / 2 for (cx, _), (sw, _) in zip(centres, sizes))
    r = max(cx + sw / 2 for (cx, _), (sw, _) in zip(centres, sizes))
    t = min(cy - sh / 2 for (_, cy), (_, sh) in zip(centres, sizes))
    b = max(cy + sh / 2 for (_, cy), (_, sh) in zip(centres, sizes))
    return angle, l, t, r - l, b - t


def bounds(box: tuple[float, float, float, float], angle: float) -> tuple[float, float, float, float]:
    """Screen bounding box (l, t, r, b) of a tilted-frame box (l, t, r, b), e.g. to crop the image."""
    if not angle:
        return box
    l, t, r, b = box
    pts = [unrotate_point(x, y, angle) for x, y in ((l, t), (r, t), (r, b), (l, b))]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)
