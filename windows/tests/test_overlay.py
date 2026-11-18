from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication

from app.config import Overlay as OverlayCfg
from app.gui.overlay import ResultOverlay, physical_to_logical, place_overlay
from app.pipeline import Segment

SCREEN = QRect(0, 0, 1920, 1080)


def test_place_below_region():
    assert place_overlay(QRect(100, 100, 400, 80), QSize(400, 120), SCREEN) == QPoint(100, 186)


def test_place_above_when_bottom_overflows():
    assert place_overlay(QRect(100, 1000, 400, 60), QSize(400, 120), SCREEN) == QPoint(100, 1000 - 6 - 120)


def test_clamp_right_edge():
    assert place_overlay(QRect(1800, 100, 100, 50), QSize(400, 120), SCREEN).x() == 1920 - 400


def test_overflow_both_ways_sticks_to_bottom_inside():
    p = place_overlay(QRect(0, 0, 400, 1080), QSize(400, 120), SCREEN)
    assert p.y() == 1080 - 120


def test_physical_to_logical_scaled_screen():
    assert physical_to_logical((300, 300, 600, 150), QRect(0, 0, 1280, 720), 1.5) == QRect(200, 200, 400, 100)


def test_physical_to_logical_second_monitor():
    # Qt keeps each screen's native origin; only distances inside it are scaled
    assert physical_to_logical((1920 + 300, 0, 300, 150), QRect(1920, 0, 1280, 720), 1.5) == QRect(2120, 0, 200, 100)


SEGS = [Segment("name", "Druvis III", None, (0, 0, 1, 1)),
        Segment("text", "A dream far too vivid.", "Một giấc mơ quá sống động.", (0, 0, 1, 1))]


def test_show_segments_and_copy(qtbot):
    w = ResultOverlay(OverlayCfg())
    qtbot.addWidget(w)
    w.show_segments(SEGS, show_source=False)
    assert "[Druvis III]" in w.text() and "Một giấc mơ quá sống động." in w.text()
    assert "A dream far too vivid." not in w.text()
    qtbot.mouseClick(w.copy_button, Qt.LeftButton)
    assert QGuiApplication.clipboard().text() == "Một giấc mơ quá sống động."


def test_show_source(qtbot):
    w = ResultOverlay(OverlayCfg())
    qtbot.addWidget(w)
    w.show_segments(SEGS, show_source=True)
    assert "A dream far too vivid." in w.text()


def test_loading_and_error_states(qtbot):
    w = ResultOverlay(OverlayCfg())
    qtbot.addWidget(w)
    w.show_loading("Đang tải model…")
    assert "Đang tải model…" in w.text() and not w.copy_button.isEnabled()
    w.show_error("Không tìm thấy model")
    assert "Không tìm thấy model" in w.text()


def test_escape_closes(qtbot):
    w = ResultOverlay(OverlayCfg())
    qtbot.addWidget(w)
    w.show_segments(SEGS, show_source=False)
    w.present(QRect(100, 100, 400, 80), SCREEN)
    assert w.isVisible()
    qtbot.keyClick(w, Qt.Key_Escape)
    assert not w.isVisible()
