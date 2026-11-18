import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication

from app.gui.selector import MIN_SIZE, RegionSelector, normalize_rect


def test_normalize_rect_any_drag_direction():
    assert normalize_rect(100, 50, 20, 10) == (20, 10, 80, 40)
    assert normalize_rect(20, 10, 100, 50) == (20, 10, 80, 40)


def test_min_size():
    assert MIN_SIZE == 8


class FakeCursor:
    def __init__(self, *points):
        self.points = list(points)

    def __call__(self):
        return self.points.pop(0)


def _drag(qtbot, sel):
    win = sel.windows[0]
    qtbot.mousePress(win, Qt.LeftButton, pos=QPoint(5, 5))
    qtbot.mouseMove(win, QPoint(50, 40))
    qtbot.mouseRelease(win, Qt.LeftButton, pos=QPoint(50, 40))


def test_one_window_per_screen_and_selection(qtbot):
    sel = RegionSelector(cursor_fn=FakeCursor((10, 10), (210, 110)))
    sel.begin()
    assert len(sel.windows) == len(QGuiApplication.screens())
    with qtbot.waitSignal(sel.selected, timeout=1000) as blocker:
        _drag(qtbot, sel)
    assert blocker.args == [(10, 10, 200, 100)]
    assert sel.windows == []


def test_tiny_selection_cancels(qtbot):
    sel = RegionSelector(cursor_fn=FakeCursor((10, 10), (14, 12)))
    sel.begin()
    with qtbot.waitSignal(sel.cancelled, timeout=1000):
        _drag(qtbot, sel)
    assert sel.windows == []


def test_escape_cancels(qtbot):
    sel = RegionSelector(cursor_fn=FakeCursor())
    sel.begin()
    with qtbot.waitSignal(sel.cancelled, timeout=1000):
        qtbot.keyClick(sel.windows[0], Qt.Key_Escape)
    assert sel.windows == []


def test_right_click_cancels(qtbot):
    sel = RegionSelector(cursor_fn=FakeCursor())
    sel.begin()
    with qtbot.waitSignal(sel.cancelled, timeout=1000):
        qtbot.mousePress(sel.windows[0], Qt.RightButton, pos=QPoint(5, 5))


@pytest.mark.local
def test_win32_helpers():
    from app.gui import win32

    x, y = win32.cursor_pos_physical()
    left, top, w, h = win32.monitor_rect_at(x, y)
    assert w > 0 and h > 0 and left <= x < left + w and top <= y < top + h
