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
