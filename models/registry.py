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
    # Phase 6: opus-mt-en-vi fine-tuned on open data (training/kaggle_finetune.ipynb); export with --hf-id
    "screentrans-en-vi": ModelSpec("models/out/screentrans-en-vi-hf", "marian", None, None),
}


def spec_for(key: str, hf_id: str | None = None) -> ModelSpec:
    """The model's spec, optionally read from another Hugging Face repo or a local folder (a fine-tuned model)."""
    from dataclasses import replace

    spec = MODELS[key]
    return replace(spec, hf_id=hf_id) if hf_id else spec
