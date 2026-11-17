import json
from pathlib import Path

import jsonschema
import pytest

from app.glossary import PLACEHOLDER, Glossary, ProperNounTracker, load_common_words

SHARED = Path(__file__).parents[2] / "shared"
COMMON = SHARED / "glossary" / "common.json"
GAME = SHARED / "glossary" / "games" / "reverse1999.json"


def _write(tmp_path, name, entries):
    p = tmp_path / name
    p.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")
    return p


def test_keep_round_trip():
    g = Glossary.load(GAME, COMMON)
    text, values = g.protect("Good morning, Timekeeper. Your HP is low.")
    assert "Timekeeper" not in text and "HP" not in text
    assert values == ["Timekeeper", "HP"]
    translated = text.replace("Good morning", "Chào buổi sáng").replace("Your", "Của bạn")
    assert g.restore(translated, values) == "Chào buổi sáng, Timekeeper. Của bạn HP is low."


def test_map_entry_restores_target(tmp_path):
    g = Glossary.load(_write(tmp_path, "g.json", [{"source": "Arcanist", "type": "map", "target": "Thuật sĩ"}]))
    text, values = g.protect("The Arcanist waits.")
    assert values == ["Thuật sĩ"]
    assert g.restore(text, values) == "The Thuật sĩ waits."


def test_game_glossary_wins_over_common(tmp_path):
    game = _write(tmp_path, "game.json", [{"source": "HP", "type": "map", "target": "Máu"}])
    _, values = Glossary.load(game, COMMON).protect("HP low")
    assert values == ["Máu"]


def test_longest_match_first():
    _, values = Glossary.load(GAME).protect("Druvis III smiled at Vertin.")
    assert values == ["Druvis III", "Vertin"]


def test_word_boundaries():
    _, values = Glossary.load(COMMON).protect("HPX and shape")
    assert values == []


def test_case_insensitive_entry(tmp_path):
    g = Glossary.load(_write(tmp_path, "g.json", [{"source": "timekeeper", "type": "keep", "case_sensitive": False}]))
    _, values = g.protect("TIMEKEEPER!")
    assert values == ["TIMEKEEPER"]


def test_case_sensitive_by_default():
    _, values = Glossary.load(GAME).protect("the vertin")
    assert values == []


def test_restore_detects_dropped_placeholder():
    g = Glossary.load(GAME)
    text, values = g.protect("Hello Vertin and Sonetto.")
    assert g.restore(text.replace(PLACEHOLDER.format(i=1), ""), values) is None


def test_restore_detects_renumbered_placeholder():
    g = Glossary.load(GAME)
    text, values = g.protect("Hello Vertin.")
    assert g.restore(text.replace(PLACEHOLDER.format(i=0), PLACEHOLDER.format(i=7)), values) is None


def test_add_keep():
    g = Glossary.load(COMMON)
    g.add_keep("Bob")
    assert g.protect("Hi Bob.")[1] == ["Bob"]


def test_glossary_files_match_schema():
    schema = json.loads((SHARED / "schemas" / "glossary.schema.json").read_text(encoding="utf-8"))
    for p in (COMMON, GAME):
        jsonschema.validate(json.loads(p.read_text(encoding="utf-8")), schema)


def test_schema_requires_target_for_map():
    schema = json.loads((SHARED / "schemas" / "glossary.schema.json").read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"version": 1, "entries": [{"source": "x", "type": "map"}]}, schema)


def test_proper_noun_tracker():
    t = ProperNounTracker(load_common_words(), min_count=3)
    assert t.observe("Hello Sonetto.") == []
    assert t.observe("Thanks Sonetto.") == []
    assert t.observe("Bye Sonetto.") == ["Sonetto"]
    assert t.observe("Again Sonetto.") == []  # reported once


def test_tracker_ignores_sentence_start_and_common_words():
    t = ProperNounTracker(load_common_words(), min_count=1)
    assert t.observe("The cat likes Water.") == []


def test_auto_keep_does_not_override_case_insensitive_game_map(tmp_path):
    g = Glossary.load(_write(tmp_path, "g.json", [
        {"source": "arcanist", "type": "map", "target": "Thuật sư", "case_sensitive": False}]))
    g.add_keep("Arcanist")
    assert g.protect("The Arcanist waits.")[1] == ["Thuật sư"]


def test_case_insensitive_game_entry_beats_common_exact(tmp_path):
    game = _write(tmp_path, "game.json", [{"source": "hp", "type": "map", "target": "Máu", "case_sensitive": False}])
    assert Glossary.load(game, COMMON).protect("HP low")[1] == ["Máu"]


def test_tracker_counts_distinct_sentences_only():
    t = ProperNounTracker(load_common_words(), min_count=3)
    for _ in range(5):
        assert t.observe("Hello Sonetto.") == []
    t.observe("Bye Sonetto.")
    assert t.observe("See you Sonetto.") == ["Sonetto"]
