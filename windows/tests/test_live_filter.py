import json
from pathlib import Path

import pytest

from app.live.filter import worth_translating
from app.text.postprocess import Paragraph

CASES = json.loads((Path(__file__).parents[2] / "shared" / "fixtures" / "live_filter" / "cases.json")
                   .read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["text"])
def test_case(case):
    l, t, r, b = case["box"]
    p = Paragraph(case["kind"], case["text"], [case["text"]], l, t, r, b, case["line_height"])
    assert worth_translating(p) == case["keep"], case["why"]
