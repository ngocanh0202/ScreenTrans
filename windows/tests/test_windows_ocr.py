import sys
import types
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.ocr.base import Line, OcrUnavailable
from app.ocr.windows_ocr import WindowsOcr

SAMPLE = Path(__file__).parents[2] / "spikes" / "ocr" / "data" / "rv_02_short.png"


def _text_image(text: str, size=(600, 80), font_size=40) -> Image.Image:
    img = Image.new("RGB", size, (0, 0, 0))
    ImageDraw.Draw(img).text((10, 10), text, font=ImageFont.truetype("segoeui.ttf", font_size), fill=(255, 255, 255))
    return img


def test_line_right_and_bottom():
    line = Line("a", 10, 20, 30, 5)
    assert (line.right, line.bottom) == (40, 25)


@pytest.mark.local
def test_reads_one_line_with_box():
    lines = WindowsOcr().recognize(_text_image("Hello world"))
    assert len(lines) == 1
    assert "Hello world" in lines[0].text
    assert 0 <= lines[0].left < 50 and lines[0].height > 20


@pytest.mark.local
def test_small_rgba_image_boxes_in_original_coordinates():
    img = Image.new("RGBA", (300, 16), (0, 0, 0, 255))
    ImageDraw.Draw(img).text((2, 0), "Hi there", font=ImageFont.truetype("segoeui.ttf", 12), fill=(255, 255, 255, 255))
    for line in WindowsOcr().recognize(img):
        assert line.right <= 300 + 1 and line.bottom <= 16 + 1


def test_missing_language_pack_raises_unavailable(monkeypatch):
    fake = types.ModuleType("winocr")

    def recognize_pil_sync(img, lang):
        raise RuntimeError("language not available")

    fake.recognize_pil_sync = recognize_pil_sync
    monkeypatch.setitem(sys.modules, "winocr", fake)
    monkeypatch.setattr("app.ocr.windows_ocr.language_available", lambda lang: False)
    with pytest.raises(OcrUnavailable, match="Language"):
        WindowsOcr().recognize(Image.new("RGB", (50, 50)))


def test_other_errors_are_not_blamed_on_language_pack(monkeypatch):
    fake = types.ModuleType("winocr")

    def recognize_pil_sync(img, lang):
        raise ValueError("bad image")

    fake.recognize_pil_sync = recognize_pil_sync
    monkeypatch.setitem(sys.modules, "winocr", fake)
    monkeypatch.setattr("app.ocr.windows_ocr.language_available", lambda lang: True)
    with pytest.raises(ValueError, match="bad image"):
        WindowsOcr().recognize(Image.new("RGB", (50, 50)))


@pytest.mark.local
def test_real_dialogue_crop():
    if not SAMPLE.is_file():
        pytest.skip("sample screenshot not present")
    lines = WindowsOcr().recognize(Image.open(SAMPLE))
    assert len(lines) == 2
    assert lines[1].text.endswith(".") and len(lines[1].text) > 10
    assert lines[0].bottom <= lines[1].top


def test_tilted_words_make_a_tilted_line():
    import math

    from app.ocr.windows_ocr import line_from_words

    c, s = math.cos(math.radians(12)), math.sin(math.radians(12))
    bw, bh = 60 * c + 20 * s, 60 * s + 20 * c
    words = [{"x": 100 + i * 80 * c - bw / 2, "y": 200 + i * 80 * s - bh / 2, "width": bw, "height": bh} for i in range(3)]
    line = line_from_words("Trail A Determined Visitor", words, scale=1.0)
    assert abs(line.angle - 12) < 0.5 and abs(line.width - 220) < 10
    flat = line_from_words("Hi there", [{"x": 10, "y": 50, "width": 40, "height": 20},
                                        {"x": 60, "y": 50, "width": 40, "height": 20}], scale=2.0)
    assert flat.angle == 0 and (flat.left, flat.top, flat.width, flat.height) == (5, 25, 45, 10)
