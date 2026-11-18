import json
from pathlib import Path

import pytest

from app.live.sentences import SentenceGate

FIXTURES = sorted((Path(__file__).parents[2] / "shared" / "fixtures" / "live_sentences").glob("*.json"))


def test_fixture_set_present():
    assert len(FIXTURES) >= 7


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    previous = None
    for step in data["steps"]:
        assert SentenceGate.done(step["sentences"], previous, step["final"]) == step["done"], step
        previous = step["sentences"]


def test_empty_block_has_nothing_done():
    assert SentenceGate.done([], None, False) == 0
    assert SentenceGate.done([], None, True) == 0
