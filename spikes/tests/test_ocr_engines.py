import sys
import types

import pytest
from PIL import Image, ImageDraw, ImageFont

from spikes.ocr import engines


def _hello_image() -> Image.Image:
    img = Image.new("RGB", (600, 80), (0, 0, 0))
    font = ImageFont.truetype("segoeui.ttf", 40)
    ImageDraw.Draw(img).text((10, 10), "Hello world", font=font, fill=(255, 255, 255))
    return img


@pytest.mark.local
def test_windows_ocr_reads_text():
    assert "hello world" in engines.windows_ocr(_hello_image()).lower()


@pytest.mark.local
def test_rapid_ocr_reads_text():
    assert "hello world" in engines.rapid_ocr(_hello_image()).lower()


def test_windows_ocr_missing_language_pack(monkeypatch):
    fake = types.ModuleType("winocr")

    def recognize_pil_sync(img, lang):
        raise RuntimeError("language not available")

    fake.recognize_pil_sync = recognize_pil_sync
    monkeypatch.setitem(sys.modules, "winocr", fake)
    with pytest.raises(engines.OcrEngineUnavailable) as exc:
        engines.windows_ocr(Image.new("RGB", (50, 50)))
    assert "Language" in str(exc.value)
