from PySide6.QtCore import QPoint, QRect, Qt

from app.config import Overlay as OverlayCfg
from app.gui.fullscreen import MIN_FONT, FullscreenOverlay, block_rect
from app.pipeline import Segment


def test_block_rect_adds_capture_origin():
    assert block_rect((10, 20, 110, 60), (1920, 0)) == (1930, 20, 100, 40)


def _overlay(qtbot, geometry=QRect(0, 0, 1920, 1080), dpr=1.0):
    w = FullscreenOverlay(OverlayCfg(), geometry, dpr)
    qtbot.addWidget(w)
    w.present()
    return w


def seg(src, tr, box, kind="text"):
    return Segment(kind, src, tr if kind == "text" else None, box)


def test_blocks_appear_as_added_at_logical_positions(qtbot):
    w = _overlay(qtbot)
    w.add_segment(seg("AUTO", "TỰ ĐỘNG", (100, 50, 180, 74)), (0, 0))
    assert len(w.blocks) == 1  # visible before finish()
    w.add_segment(seg("Druvis III", None, (557, 763, 706, 793), kind="name"), (0, 0))
    w.add_segment(seg("Hello there.", "Xin chào.", (546, 828, 1181, 859)), (0, 0))
    assert [b.rect for b in w.blocks] == [QRect(100, 50, 80, 24), QRect(557, 763, 149, 30), QRect(546, 828, 635, 31)]
    assert w.translating
    w.finish()
    assert not w.translating


def test_scaled_screen(qtbot):
    w = _overlay(qtbot, QRect(0, 0, 1280, 720), 1.5)
    w.add_segment(seg("Hi.", "Chào.", (300, 300, 900, 450)), (0, 0))
    assert w.blocks[0].rect == QRect(200, 200, 400, 100)


def test_long_text_shrinks_and_elides(qtbot):
    w = _overlay(qtbot)
    w.add_segment(seg("x", "rất dài " * 60, (0, 0, 120, 20)), (0, 0))
    b = w.blocks[0]
    assert b.font_size >= MIN_FONT and b.text.endswith("…")


def test_click_block_opens_detail_and_escape_closes(qtbot):
    w = _overlay(qtbot)
    w.add_segment(seg("Hello there.", "Xin chào.", (100, 100, 400, 140)), (0, 0))
    qtbot.mouseClick(w, Qt.LeftButton, pos=QPoint(150, 120))
    assert w.detail is not None and "Hello there." in w.detail.text()
    qtbot.keyClick(w, Qt.Key_Escape)
    assert not w.isVisible()


def test_click_empty_area_closes(qtbot):
    w = _overlay(qtbot)
    w.add_segment(seg("Hello.", "Chào.", (100, 100, 400, 140)), (0, 0))
    qtbot.mouseClick(w, Qt.LeftButton, pos=QPoint(900, 900))
    assert not w.isVisible()
