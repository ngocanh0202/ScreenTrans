"""Translation models used by ScreenTrans (EN -> VI)."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ModelSpec:
    hf_id: str
    kind: Literal["marian", "mbart"]
    src_lang: str | None
    tgt_prefix: str | None


MODELS: dict[str, ModelSpec] = {
    "opus-mt-en-vi": ModelSpec("Helsinki-NLP/opus-mt-en-vi", "marian", None, None),
    "vinai-en2vi": ModelSpec("vinai/vinai-translate-en2vi-v2", "mbart", "en_XX", "vi_VN"),
}
