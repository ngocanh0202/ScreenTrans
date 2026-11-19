from PIL import Image


from app.cache import TranslationCache
from app.glossary import Glossary
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
    assert a.shape == (30, 160)
    assert diff(a, gray_thumb(black)) == 0
    assert diff(a, b) == 30 * 160  # every cell changed
    assert diff(a, gray_thumb(Image.new("RGB", (100, 100)))) == float("inf")
    dot = black.copy()
    dot.putpixel((5, 5), (255, 255, 255))
    assert diff(a, gray_thumb(dot)) < 5


def test_live_scope_persists_and_maps_old_modes_to_region(tmp_path):
    from app.live.regions import load_live_scope, save_live_scope

    assert load_live_scope(tmp_path) == "region"
    save_live_scope(tmp_path, "screen")
    assert load_live_scope(tmp_path) == "screen"
    for old in ("dialogue", "area", "junk"):
        (tmp_path / "live_mode.txt").write_text(old, encoding="utf-8")
        assert load_live_scope(tmp_path) == "region"


def test_area_overlay_draws_and_removes_blocks(qtbot):
    from PySide6.QtCore import QRect, Qt

    from app.config import Overlay
    from app.gui.live_overlay import AreaOverlay

    ao = AreaOverlay(Overlay(), QRect(0, 0, 1920, 1080), 1.0)
    qtbot.addWidget(ao)
    assert ao.windowFlags() & Qt.WindowTransparentForInput
    ao.set_block("b1", "Chào.", (0, 0, 100, 20), (100, 100))
    ao.set_block("b2", "Druvis III", (0, 30, 100, 50), (100, 100), "name")
    assert ao.blocks["b1"].text == "Chào." and ao.isVisible()
    ao.remove_block("b1")
    assert list(ao.blocks) == ["b2"]


def test_area_overlay_uses_the_source_size_and_colours(qtbot):
    from PySide6.QtCore import QRect

    from app.config import Overlay
    from app.gui.live_overlay import AreaOverlay
    from app.live.style import BlockStyle

    ao = AreaOverlay(Overlay(), QRect(0, 0, 1920, 1080), 1.5)
    qtbot.addWidget(ao)
    ao.set_block("b1", "Chào.", (0, 0, 300, 45), (0, 0), font_px=36,
                 colors=BlockStyle((20, 20, 20), (250, 250, 250)))
    b = ao.blocks["b1"]
    assert b.px == 24  # 36 physical px on a 150% screen
    assert b.fg.getRgb()[:3] == (20, 20, 20) and b.bg.getRgb()[:3] == (250, 250, 250) and b.bg.alpha() == 255
    ao.set_block("b2", "Một câu khá dài " * 6, (0, 100, 300, 145), (0, 0), font_px=36)
    grown = ao.blocks["b2"]
    assert grown.px == 24 and grown.draw_height > 45  # long_text "grow": the box extends, the font stays
    assert grown.fg.getRgb()[:3] == (255, 255, 255)  # no sampled colours: white on dark
    shrink = AreaOverlay(Overlay(long_text="shrink"), QRect(0, 0, 1920, 1080), 1.5)
    qtbot.addWidget(shrink)
    shrink.set_block("b2", "Một câu khá dài " * 6, (0, 100, 300, 145), (0, 0), font_px=36)
    assert shrink.blocks["b2"].px < 24 and shrink.blocks["b2"].draw_height <= int(30 * 1.5) + 1


def test_tilted_block_is_drawn_rotated(qtbot):
    from PySide6.QtCore import QRect

    from app.config import Overlay
    from app.gui.live_overlay import AreaOverlay

    ao = AreaOverlay(Overlay(), QRect(0, 0, 1920, 1080), 1.0)
    qtbot.addWidget(ao)
    ao.set_block("b1", "Một người khách kiên trì", (100, 300, 700, 330), (0, 0), font_px=24, angle=-8.0)
    assert ao.blocks["b1"].angle == -8.0
    ao.grab()  # paints with the rotation without errors


def test_text_scale_multiplies_the_source_size(qtbot):
    from PySide6.QtCore import QRect

    from app.config import Overlay
    from app.gui.live_overlay import AreaOverlay

    ao = AreaOverlay(Overlay(text_scale=1.5), QRect(0, 0, 1920, 1080), 1.0)
    qtbot.addWidget(ao)
    ao.set_block("b", "Chào.", (0, 0, 400, 40), (0, 0), font_px=20)
    assert ao.blocks["b"].px == 30


def test_a_short_line_appearing_on_a_full_screen_counts_as_a_change():
    """Regression: the mean over a 64-px thumbnail hid new dialogue (diff ~0.4), so only the first line was read."""
    from PIL import ImageDraw, ImageFont

    screen = Image.new("RGB", (2048, 942), (40, 44, 52))
    talk = screen.copy()
    ImageDraw.Draw(talk).text((600, 820), "Hi.", fill=(235, 235, 235), font=ImageFont.load_default(36))
    assert diff(gray_thumb(screen), gray_thumb(talk)) > 5
    # JPEG-like noise / a 2 % brightness flicker everywhere is not a change
    flicker = screen.point(lambda v: min(255, int(v * 1.02) + 1))
    assert diff(gray_thumb(screen), gray_thumb(flicker)) <= 5
