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
