"""CTranslate2 int8 CPU translator for Marian (opus-mt) and mBART (vinai) exports."""
import json
import re
import time
from pathlib import Path
from typing import Callable

from app.translate.base import META_FILE, ModelNotFound

MAX_INPUT = 512
MAX_OUTPUT = 256
CHUNK_TOKENS = 150  # longer inputs are split so the 256-token output cap never cuts the translation


def split_long(text: str, count_tokens: Callable[[str], int], limit: int = CHUNK_TOKENS) -> list[str]:
    """Split text into pieces of at most `limit` tokens: at , ; : first, then between words."""
    if count_tokens(text) <= limit:
        return [text]
    out: list[str] = []
    current = ""
    for piece in re.split(r"(?<=[,;:])\s+", text):
        candidate = f"{current} {piece}".strip()
        if count_tokens(candidate) <= limit:
            current = candidate
            continue
        if current:
            out.append(current)
        if count_tokens(piece) <= limit:
            current = piece
            continue
        current = ""
        for word in piece.split():  # no punctuation to cut at: fill word windows
            candidate = f"{current} {word}".strip()
            if current and count_tokens(candidate) > limit:
                out.append(current)
                current = word
            else:
                current = candidate
    if current:
        out.append(current)
    return out


class Ct2Translator:
    def __init__(self, model_dir: Path, beam_size: int = 2, intra_threads: int = 2):
        model_dir = Path(model_dir)
        meta_path = model_dir / META_FILE
        if not (model_dir / "model.bin").is_file() or not meta_path.is_file():
            raise ModelNotFound(
                f"No translation model in {model_dir}. Export one with "
                f"`python -m models.export ct2 vinai-en2vi` (or opus-mt-en-vi) and pass --model-dir, "
                f"or let the app download it from the manifest."
            )
        import ctranslate2
        from transformers import AutoTokenizer

        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.model_id: str = self.meta["id"]
        self.beam_size = beam_size
        kwargs = {"src_lang": self.meta["src_lang"]} if self.meta.get("src_lang") else {}
        self._tok = AutoTokenizer.from_pretrained(str(model_dir), **kwargs)
        self._ct2 = ctranslate2.Translator(
            str(model_dir), device="cpu", compute_type="int8", intra_threads=intra_threads, inter_threads=1
        )

    def translate(self, texts: list[str]) -> list[str]:
        out = [""] * len(texts)
        count = lambda t: len(self._tok.encode(t))  # noqa: E731
        todo = [(i, piece) for i, t in enumerate(texts) if t.strip() for piece in split_long(t.strip(), count)]
        if not todo:
            return out
        src = [self._tok.convert_ids_to_tokens(self._tok.encode(t)) for _, t in todo]
        kwargs = {"beam_size": self.beam_size, "max_input_length": MAX_INPUT, "max_decoding_length": MAX_OUTPUT}
        prefix = self.meta.get("tgt_prefix")
        if prefix:
            kwargs["target_prefix"] = [[prefix]] * len(src)
        for (i, _), result in zip(todo, self._ct2.translate_batch(src, **kwargs)):
            tokens = [t for t in result.hypotheses[0] if t != prefix]
            piece = self._tok.decode(self._tok.convert_tokens_to_ids(tokens), skip_special_tokens=True).strip()
            out[i] = f"{out[i]} {piece}".strip()
        return out

    def warm_up(self) -> float:
        t0 = time.perf_counter()
        self.translate(["Hello."])
        return (time.perf_counter() - t0) * 1000
