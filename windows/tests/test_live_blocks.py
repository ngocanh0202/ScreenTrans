import json
from pathlib import Path

import pytest

from app.live.blocks import BlockTracker, RateLimiter
from app.text.postprocess import Paragraph

FIXTURES = sorted((Path(__file__).parents[2] / "shared" / "fixtures" / "live_blocks").glob("*.json"))


def para(p):
    l, t, r, b = p["box"]
    return Paragraph("text", p["text"], [p["text"]], l, t, r, b)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    tracker = BlockTracker(**data["params"])
    for step in data["steps"]:
        diff = tracker.update([para(p) for p in step["paragraphs"]])
        got = {k: [b.text for b in getattr(diff, k)] for k in ("added", "kept", "removed")}
        assert got == step["expected"]


def test_fixture_set_present():
    assert len(FIXTURES) >= 5


def test_kept_block_keeps_its_key():
    tr = BlockTracker()
    a = para({"text": "Hi.", "box": [0, 0, 100, 30]})
    first = tr.update([a]).added[0]
    assert tr.update([a]).kept[0].key == first.key


def test_rate_limiter():
    rl = RateLimiter(1000)
    assert rl.allow(0) and not rl.allow(500) and rl.allow(1000)
