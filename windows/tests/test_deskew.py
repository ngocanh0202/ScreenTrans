import math

import pytest

from app.ocr.deskew import bounds, from_corners, from_words, rotate_point, unrotate_point


def _corners(cx, cy, w, h, angle):
    """Screen corners (clockwise from top-left) of a w x h box centred at (cx, cy) tilted by `angle`."""
    dcx, dcy = rotate_point(cx, cy, angle)
    pts = [(dcx - w / 2, dcy - h / 2), (dcx + w / 2, dcy - h / 2), (dcx + w / 2, dcy + h / 2), (dcx - w / 2, dcy + h / 2)]
    return [unrotate_point(x, y, angle) for x, y in pts]


def test_rotate_and_unrotate_are_inverse():
    x, y = unrotate_point(*rotate_point(123.0, 45.0, 17.0), 17.0)
    assert (x, y) == pytest.approx((123.0, 45.0))


def test_from_corners_gives_back_the_straight_box():
    pts = _corners(300, 200, 200, 30, 15)
    left, top, width, height = from_corners(pts, 15)
    assert (width, height) == pytest.approx((200, 30))
    dcx, dcy = rotate_point(300, 200, 15)
    assert (left + width / 2, top + height / 2) == pytest.approx((dcx, dcy))


def test_from_words_measures_the_slope():
    words = []
    c, s = math.cos(math.radians(10)), math.sin(math.radians(10))
    bw, bh = 60 * c + 20 * s, 60 * s + 20 * c  # OCR gives the axis-aligned box of a tilted 60x20 word
    for i in range(3):  # three words along a 10 degree line
        cx = 100 + i * 80 * c
        cy = 200 + i * 80 * s
        words.append((cx - bw / 2, cy - bh / 2, bw, bh))
    angle, left, top, width, height = from_words(words)
    assert angle == pytest.approx(10, abs=0.5)
    assert width == pytest.approx(220, abs=8) and height == pytest.approx(20, abs=8)


def test_from_words_straight_line_keeps_the_plain_box():
    angle, left, top, width, height = from_words([(10, 50, 40, 20), (60, 51, 40, 20)])
    assert angle == 0 and (left, top, width, height) == (10, 50, 90, 21)


def test_bounds_of_a_tilted_box_contains_its_corners():
    l, t, r, b = 100.0, 200.0, 300.0, 230.0
    xl, yt, xr, yb = bounds((l, t, r, b), 20)
    for x, y in [(l, t), (r, t), (r, b), (l, b)]:
        sx, sy = unrotate_point(x, y, 20)
        assert xl - 1e-6 <= sx <= xr + 1e-6 and yt - 1e-6 <= sy <= yb + 1e-6
