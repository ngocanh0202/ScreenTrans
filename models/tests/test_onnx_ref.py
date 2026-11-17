import json
from pathlib import Path

import pytest

from models.registry import MODELS
from models.verify import load_sentences

ONNX_DIR = Path(__file__).parents[1] / "out" / "opus-mt-en-vi-onnx"

pytestmark = pytest.mark.local


@pytest.fixture(scope="module")
def tok():
    from transformers import MarianTokenizer

    return MarianTokenizer.from_pretrained(str(ONNX_DIR))


def test_greedy_ends_with_eos(tok):
    from models.onnx_ref import greedy_translate

    out = greedy_translate(["Hello."], ONNX_DIR)
    assert len(out) == 1
    assert out[0][-1] == tok.eos_token_id


def test_greedy_matches_transformers(tok):
    import sacrebleu

    from models.onnx_ref import greedy_translate
    from models.verify import reference_translate

    texts = load_sentences()[:10]
    ids = greedy_translate(texts, ONNX_DIR)
    hyp = [tok.decode(i, skip_special_tokens=True) for i in ids]
    ref = reference_translate(MODELS["opus-mt-en-vi"], texts)
    chrf = [sacrebleu.sentence_chrf(h, [r]).score for h, r in zip(hyp, ref)]
    assert sum(chrf) / len(chrf) >= 90


def test_greedy_respects_max_len():
    from models.onnx_ref import greedy_translate

    long_text = " ".join(["The cat sat on the mat and looked at the stars."] * 30)
    out = greedy_translate([long_text], ONNX_DIR, max_len=40)
    assert len(out[0]) <= 40


def test_sp_export_has_pieces():
    data = json.loads((ONNX_DIR / "sp_source.json").read_text(encoding="utf-8"))
    assert data["normalizer"] == "nmt_nfkc"
    assert len(data["pieces"]) > 1000
    assert isinstance(data["unk_id"], int)


def test_greedy_truncates_overlong_input():
    from models.onnx_ref import greedy_translate

    text = "The cat sat on the mat. " * 120  # ~841 source ids > model_max_length 512
    out = greedy_translate([text], ONNX_DIR, max_len=20)
    assert 0 < len(out[0]) <= 20


def test_tokenizer_cases_written_with_tricky_text():
    from models.onnx_ref import TOKENIZER_CASES, write_tokenizer_cases

    path = write_tokenizer_cases()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == len(TOKENIZER_CASES)
    assert any("\ufeff" in c["text"] for c in data)
    assert all(c["src_ids"][-1] == 0 for c in data)
