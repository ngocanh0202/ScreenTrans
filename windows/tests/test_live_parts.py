from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize

from app.cache import TranslationCache
from app.glossary import Glossary
from app.gui.live_overlay import place_above
from app.live.regions import load_live_regions, save_live_regions
from app.live.thumb import diff, gray_thumb
from app.pipeline import Pipeline
from app.text.postprocess import Paragraph
from fakes import FakeOcr, FakeTranslator


def _p(text, top=0.0):
    from app.text.postprocess import split_sentences
    return Paragraph("text", text, split_sentences(text), 0, top, 100, top + 20)


def test_iter_sentences_yields_after_each_sentence_with_placeholders():
    tr = FakeTranslator(lambda s: "VI " + s)
    p = Pipeline(FakeOcr([]), tr, Glossary([]), TranslationCache(10, None))
    name = Paragraph("name", "Druvis III", [], 0, 0, 10, 10)
    steps = list(p.iter_sentences([name, _p("One. Two.", 20)]))
    assert [s[1].translation for s in steps] == ["VI One. …", "VI One. VI Two."]
    assert all(s[0].kind == "name" for s in steps)
    assert [c for c in tr.calls] == [["One."], ["Two."]]


def test_iter_sentences_with_no_text_yields_once():
    p = Pipeline(FakeOcr([]), FakeTranslator(str.upper), Glossary([]), TranslationCache(10, None))
    assert list(p.iter_sentences([])) == [[]]


def test_live_regions_round_trip(tmp_path):
    assert load_live_regions(tmp_path) == []
    save_live_regions(tmp_path, [(10, 20, 300, 80), (-1920, 0, 100, 50)])
    assert load_live_regions(tmp_path) == [(10, 20, 300, 80), (-1920, 0, 100, 50)]
    (tmp_path / "live_regions.json").write_text("garbage", encoding="utf-8")
    assert load_live_regions(tmp_path) == []


def test_thumb_diff():
    black = Image.new("RGB", (640, 120), (0, 0, 0))
    white = Image.new("RGB", (640, 120), (255, 255, 255))
    a, b = gray_thumb(black), gray_thumb(white)
    assert a.shape == (12, 64)
    assert diff(a, gray_thumb(black)) == 0
    assert round(diff(a, b)) == 255
    assert diff(a, gray_thumb(Image.new("RGB", (100, 100)))) == float("inf")
    dot = black.copy()
    dot.putpixel((5, 5), (255, 255, 255))
    assert diff(a, gray_thumb(dot)) < 5


def test_place_above_then_below():
    screen = QRect(0, 0, 1920, 1080)
    assert place_above(QRect(100, 500, 400, 80), QSize(400, 100), screen) == QPoint(100, 500 - 6 - 100)
    assert place_above(QRect(100, 50, 400, 80), QSize(400, 100), screen) == QPoint(100, 50 + 80 + 6)


def test_live_mode_persists_and_defaults_to_dialogue(tmp_path):
    from app.live.regions import load_live_mode, save_live_mode

    assert load_live_mode(tmp_path) == "dialogue"
    save_live_mode(tmp_path, "area")
    assert load_live_mode(tmp_path) == "area"
    (tmp_path / "live_mode.txt").write_text("junk", encoding="utf-8")
    assert load_live_mode(tmp_path) == "dialogue"


def test_live_overlays_show_and_remove(qtbot):
    from PySide6.QtCore import QRect, Qt

    from app.config import Overlay
    from app.gui.live_overlay import AreaOverlay, LiveOverlay
    from app.pipeline import Segment

    screen = QRect(0, 0, 1920, 1080)
    lo = LiveOverlay(Overlay(), QRect(100, 500, 400, 80), screen)
    qtbot.addWidget(lo)
    assert lo.windowFlags() & Qt.WindowTransparentForInput
    lo.show_segments([Segment("text", "Hi.", "Chào.", (0, 0, 10, 10))])
    assert "Chào." in lo.text() and lo.isVisible() and lo.geometry().bottom() < 500
    ao = AreaOverlay(Overlay(), screen, 1.0)
    qtbot.addWidget(ao)
    ao.set_block("b1", Segment("text", "Hi.", "Chào.", (0, 0, 100, 20)), (100, 100))
    assert "b1" in ao.blocks and ao.isVisible()
    ao.remove_block("b1")
    assert ao.blocks == {}
