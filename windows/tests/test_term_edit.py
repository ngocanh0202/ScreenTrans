"""Editing a game's glossary in Settings: rules in shared/fixtures/term_edit (Kotlin TermEdit.kt passes them too)."""
import json
from pathlib import Path

import pytest

from app.text.term_edit import clean, dump, parse

FIX = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "term_edit"


def _rows(rows):
    return None if rows is None else [tuple(r) for r in rows]


@pytest.mark.parametrize("case", json.loads((FIX / "parse.json").read_text(encoding="utf-8")), ids=lambda c: c["name"])
def test_parse(case):
    assert parse(case["text"]) == _rows(case["rows"])


@pytest.mark.parametrize("case", json.loads((FIX / "clean.json").read_text(encoding="utf-8")), ids=lambda c: c["name"])
def test_clean(case):
    assert clean(_rows(case["rows"])) == _rows(case["expected"])


def test_dump_reads_back_and_matches_the_glossary_format():
    rows = [("Vertin", None, True), ("storm", "Bão", False)]
    data = dump(rows)
    assert data == {"entries": [{"source": "Vertin", "type": "keep", "case_sensitive": True},
                                {"source": "storm", "type": "map", "target": "Bão", "case_sensitive": False}]}
    assert parse(json.dumps(data)) == rows
