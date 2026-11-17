import json
from pathlib import Path

import pytest

from app.ocr.base import Line
from app.text.postprocess import postprocess, split_sentences

FIXTURES = sorted((Path(__file__).parents[2] / "shared" / "fixtures" / "postprocess").glob("*.json"))


def test_fixture_set_is_present():
    assert len(FIXTURES) >= 8


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [Line(l["text"], *l["box"]) for l in data["lines"]]
    got = [{"kind": p.kind, "text": p.text, "sentences": p.sentences} for p in postprocess(lines)]
    assert got == data["expected"]


@pytest.mark.parametrize("text,expected", [
    ("Yes. Here we go.", ["Yes.", "Here we go."]),
    ("Wait... what? No!", ["Wait... what?", "No!"]),
    ("Dr. Who is here. Mrs. Lee too.", ["Dr. Who is here.", "Mrs. Lee too."]),
    ("He said “go.” Then left.", ["He said “go.”", "Then left."]),
    ("Vertin ... was the last to arrive.", ["Vertin ... was the last to arrive."]),
    ("", []),
])
def test_split_sentences(text, expected):
    assert split_sentences(text) == expected


def test_empty_input():
    assert postprocess([]) == []
