from pathlib import Path

import pytest

from app.translate.base import ModelNotFound
from app.translate.ct2 import Ct2Translator

REPO = Path(__file__).parents[2]
VINAI = REPO / "models" / "out" / "vinai-en2vi-ct2"


def test_missing_model_dir_raises(tmp_path):
    with pytest.raises(ModelNotFound) as e:
        Ct2Translator(tmp_path / "nope")
    assert "models.export ct2" in str(e.value)


def _vinai():
    if not (VINAI / "screentrans_model.json").is_file():
        pytest.skip("vinai CT2 model with screentrans_model.json not exported")
    return Ct2Translator(VINAI)


@pytest.mark.local
def test_vinai_batch_with_blank():
    out = _vinai().translate(["We have to leave right now.", "  ", "Good morning, Timekeeper."])
    assert len(out) == 3 and out[1] == ""
    assert out[0] and out[2] and not any("vi_VN" in o for o in out)


@pytest.mark.local
def test_vinai_overlong_input_does_not_crash():
    out = _vinai().translate(["The cat sat on the mat. " * 120])
    assert out[0].strip()


@pytest.mark.local
def test_warm_up_reports_ms():
    t = _vinai()
    assert t.model_id == "vinai-en2vi"
    assert t.warm_up() > 0


def test_split_long_keeps_short_text():
    from app.translate.ct2 import split_long

    assert split_long("Hello there.", lambda s: len(s.split()), 5) == ["Hello there."]


def test_split_long_cuts_at_punctuation_then_words():
    from app.translate.ct2 import split_long

    text = "a b c, d e f, g h i j k l m n"
    parts = split_long(text, lambda s: len(s.split()), 4)
    assert " ".join(parts) == text
    assert all(len(p.split()) <= 4 for p in parts)
    assert parts[0] == "a b c,"


@pytest.mark.local
def test_vinai_very_long_sentence_keeps_its_end():
    text = ", ".join(f"clause {i} is red" for i in range(1, 81)) + "."
    out = _vinai().translate([text])[0]
    assert "80" in out
