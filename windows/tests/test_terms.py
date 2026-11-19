"""Term picking rules (shared/fixtures/terms)."""
import json
from pathlib import Path

import pytest

from app.glossary import load_common_words
from app.text.terms import span, suggest_names, tokens

FIX = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "terms"
COMMON = load_common_words()


@pytest.mark.parametrize("case", json.loads((FIX / "span.json").read_text(encoding="utf-8")),
                         ids=lambda c: c["expected"])
def test_span(case):
    assert span(tokens(case["sentence"]), case["from"], case["to"]) == case["expected"]


@pytest.mark.parametrize("case", json.loads((FIX / "suggest.json").read_text(encoding="utf-8")),
                         ids=lambda c: c["name"])
def test_suggest_names(case):
    assert suggest_names(case["sentences"], COMMON, set(case["known"])) == case["expected"]
