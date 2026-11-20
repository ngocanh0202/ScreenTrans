import json
from pathlib import Path

import numpy as np
import pytest

from app.live.style import BlockStyle, font_px_for, sample_style

FIXTURES = sorted((Path(__file__).parents[2] / "shared" / "fixtures" / "live_style").glob("*.json"))


def pixels(data) -> np.ndarray:
    return np.array([[[int(c[i:i + 2], 16) for i in (0, 2, 4)] for c in row] for row in data["pixels"]], dtype=np.uint8)


def test_fixture_set_present():
    assert len(FIXTURES) >= 4


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    got = sample_style(pixels(data))
    exp = data["expected"]
    if exp is None:
        assert got is None
    else:
        assert got is not None
        assert all(abs(a - b) <= 8 for a, b in zip(got.text, exp["text"]))
        assert all(abs(a - b) <= 8 for a, b in zip(got.bg, exp["bg"]))


def test_font_size_follows_the_source_line_height():
    assert font_px_for(30.0) == pytest.approx(24.0)
    assert font_px_for(0.0) is None  # unknown line height: keep the configured size


def test_paragraph_keeps_the_median_line_height():
    from app.ocr.base import Line
    from app.text.postprocess import postprocess

    lines = [Line("Where are you going? The", 20, 100, 400, 30), Line("station is closed today.", 20, 134, 380, 32)]
    (p,) = postprocess(lines)
    assert p.line_height == pytest.approx(31.0)


def test_block_style_dataclass():
    s = BlockStyle((1, 2, 3), (4, 5, 6))
    assert s.text == (1, 2, 3) and s.bg == (4, 5, 6)


def test_style_cells_match_the_shared_fixtures():
    import json
    from pathlib import Path

    from app.live.style import style_cell

    fix = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "live_style_cells" / "cells.json"
    for c in json.loads(fix.read_text(encoding="utf-8")):
        assert style_cell(tuple(c["box"]), tuple(c["size"]), c["kind"]) == c["cell"], c["name"]
