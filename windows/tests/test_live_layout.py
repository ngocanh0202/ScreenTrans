"""Live translation box layout: rules and cases in shared/fixtures/live_layout (the Kotlin Layout.kt passes them too)."""
import json
from pathlib import Path

import pytest

from app.live.layout import separate, widen

FIX = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "live_layout"


def greedy_lines(words, space):
    def lines(width):
        n, cur = 0, None
        for w in words:
            if cur is not None and cur + space + w <= width:
                cur += space + w
            else:
                n, cur = n + 1, w
        return n
    return lines


@pytest.mark.parametrize("case", json.loads((FIX / "widen.json").read_text(encoding="utf-8")), ids=lambda c: c["name"])
def test_widen(case):
    lines = greedy_lines(case["words"], case["space"])
    assert widen(case["width"], lines, case["room"], case["px"]) == case["expected"]


@pytest.mark.parametrize("case", json.loads((FIX / "separate.json").read_text(encoding="utf-8")), ids=lambda c: c["name"])
def test_separate(case):
    got = separate([tuple(r) for r in case["rects"]], case["gap"])
    assert [list(r) for r in got] == case["expected"]
