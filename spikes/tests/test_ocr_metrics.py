from PIL import Image

from spikes.ocr.metrics import cer, prepare_image


def test_cer_identical():
    assert cer("We have to leave.", "We  have to leave.") == 0.0


def test_cer_one_substitution():
    assert cer("abcd", "abxd") == 0.25


def test_cer_empty_ref():
    assert cer("", "") == 0.0
    assert cer("", "x") == 1.0


def test_prepare_image_drops_alpha_and_upscales():
    img = Image.new("RGBA", (100, 16), (0, 0, 0, 0))
    out = prepare_image(img, min_height=32)
    assert out.mode == "RGB"
    assert out.size == (200, 32)
