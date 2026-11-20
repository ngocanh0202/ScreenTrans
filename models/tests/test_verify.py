from models.registry import MODELS
from models.verify import agreement, leaked_lang_tokens, strip_prefix


def test_strip_prefix_removes_repeated_lang_token():
    assert strip_prefix(["vi_VN", "vi_VN", "▁Xin", "▁chào"], "vi_VN") == ["▁Xin", "▁chào"]


def test_strip_prefix_none():
    assert strip_prefix(["▁a"], None) == ["▁a"]


def test_agreement_normalizes_whitespace():
    assert agreement(["Xin  chào", "b"], ["Xin chào", "c"]) == 0.5


def test_registry_vinai_lang_tokens():
    spec = MODELS["vinai-en2vi"]
    assert (spec.src_lang, spec.tgt_prefix) == ("en_XX", "vi_VN")


def test_leaked_lang_tokens_counts_raw_tokens_after_prefix():
    assert leaked_lang_tokens(["vi_VN", "▁Xin", "vi_VN", "▁chào"], "vi_VN") == 1


def test_leaked_lang_tokens_none_prefix():
    assert leaked_lang_tokens(["▁a"], None) == 0


def test_model_meta_for_vinai_ct2():
    from models.export import model_meta

    assert model_meta("vinai-en2vi", "ct2") == {
        "id": "vinai-en2vi", "kind": "mbart", "format": "ct2", "src_lang": "en_XX", "tgt_prefix": "vi_VN"}


def test_model_meta_for_opus_onnx():
    from models.export import model_meta

    assert model_meta("opus-mt-en-vi", "onnx")["kind"] == "marian"


def test_fine_tuned_model_exports_from_any_hf_id_or_folder():  # Phase 6 (RF5)
    from models.export import model_meta
    from models.registry import MODELS, spec_for

    assert MODELS["screentrans-en-vi"].kind == "marian" and MODELS["screentrans-en-vi"].tgt_prefix is None
    assert spec_for("screentrans-en-vi", "someone/my-en-vi").hf_id == "someone/my-en-vi"
    assert spec_for("opus-mt-en-vi").hf_id == "Helsinki-NLP/opus-mt-en-vi"
    assert model_meta("screentrans-en-vi", "onnx") == {"id": "screentrans-en-vi", "kind": "marian", "format": "onnx",
                                                       "src_lang": None, "tgt_prefix": None}
