import pytest

from app.capture import capture_region, enable_dpi_awareness, parse_region


def test_parse_region():
    assert parse_region("10,20,300,40") == (10, 20, 300, 40)
    assert parse_region(" -1920, 0, 100, 50 ") == (-1920, 0, 100, 50)


@pytest.mark.parametrize("bad", ["10,20,0,40", "a,b", "1,2,3", "1,2,3,-4"])
def test_parse_region_rejects(bad):
    with pytest.raises(ValueError):
        parse_region(bad)


def test_enable_dpi_awareness_is_idempotent():
    enable_dpi_awareness()
    enable_dpi_awareness()


@pytest.mark.local
def test_capture_region_size_and_mode():
    img = capture_region(0, 0, 120, 50)
    assert img.size == (120, 50) and img.mode == "RGB"
