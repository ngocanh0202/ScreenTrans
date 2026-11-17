"""Reference greedy decoder over the exported ONNX Marian model.

This is the behaviour the Kotlin decoder must reproduce exactly.
Usage: python -m models.onnx_ref golden   -> models/out/golden_opus.json
"""
import json
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "out"
ONNX_DIR = OUT / "opus-mt-en-vi-onnx"
MAX_SRC = 512  # Marian model_max_length: longer sources overflow the positional embeddings

# Text the Kotlin tokenizer must encode exactly like spm nmt_nfkc (golden_tokenizer.json).
TOKENIZER_CASES = [
    "Hello   world",
    "tab\tseparated\ttext",
    "line one\nline two\r\nline three",
    "\ufeffBOM at start",
    "zero\u200bwidth space",
    "left\u200eto\u200fright marks",
    "no\u00a0break and\u3000ideographic space",
    "en\u2002em\u2003thin\u2009spaces",
    "line\u2028sep and para\u2029sep",
    "literal \u2581 lower block",
    "replacement \ufffd char",
    "vertical\x0btab and \x1cfile sep",
    "next\x85line",
    "soft\u00adhyphen and zw\u200cnj\u200djoiner",
    "word\u2060joiner",
    "\u201cCurly quotes\u201d and \u2018single\u2019",
    "Ellipsis\u2026 and dash \u2014 here",
    "\u2605\u2605 stars \u2605",
    "Fullwidth \uff21\uff22\uff23 \uff11\uff12\uff13",
    "ligature \ufb01ne",
    "emoji \U0001f600 face",
    "  leading and trailing  ",
    "Vi\u1ec7t Nam c\u00f3 d\u1ea5u",
]


class OnnxMarian:
    def __init__(self, model_dir: Path, threads: int = 2):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.enc = ort.InferenceSession(str(model_dir / "encoder_model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(model_dir / "decoder_model_merged.onnx"), opts, providers=["CPUExecutionProvider"])
        cfg = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        self.start_id = cfg["decoder_start_token_id"]
        self.eos_id = cfg["eos_token_id"]
        self.pad_id = cfg["pad_token_id"]
        self.heads = cfg["decoder_attention_heads"]
        self.head_dim = cfg["d_model"] // self.heads
        self.past_names = [i.name for i in self.dec.get_inputs() if i.name.startswith("past_key_values")]
        self.present_names = [o.name for o in self.dec.get_outputs() if o.name.startswith("present")]

    def greedy(self, src_ids: list[int], max_len: int = 256) -> list[int]:
        ids = np.array([src_ids], dtype=np.int64)
        mask = np.ones_like(ids)
        enc_out = self.enc.run(None, {"input_ids": ids, "attention_mask": mask})[0]
        past = {n: np.zeros((1, self.heads, 0, self.head_dim), dtype=np.float32) for n in self.past_names}
        use_cache = False
        last = self.start_id
        out: list[int] = []
        while len(out) < max_len:
            feeds = {
                "input_ids": np.array([[last]], dtype=np.int64),
                "encoder_attention_mask": mask,
                "encoder_hidden_states": enc_out,
                "use_cache_branch": np.array([use_cache]),
                **past,
            }
            results = self.dec.run(None, feeds)
            logits = results[0][0, -1].copy()
            logits[self.pad_id] = -np.inf  # Marian generation forbids the pad token
            nxt = int(np.argmax(logits))
            out.append(nxt)
            if nxt == self.eos_id:
                break
            presents = dict(zip(self.present_names, results[1:]))
            new_past = {}
            for name in self.past_names:
                pname = name.replace("past_key_values", "present")
                # on cache steps the encoder KV outputs are dummies; keep the first ones
                if use_cache and ".encoder." in name:
                    new_past[name] = past[name]
                else:
                    new_past[name] = presents[pname]
            past = new_past
            use_cache = True
            last = nxt
        return out


def greedy_translate(texts: list[str], model_dir: Path, max_len: int = 256) -> list[list[int]]:
    from transformers import MarianTokenizer

    tok = MarianTokenizer.from_pretrained(str(model_dir))
    model = OnnxMarian(model_dir)
    return [model.greedy(tok(t, truncation=True, max_length=MAX_SRC)["input_ids"], max_len) for t in texts]


def write_golden() -> Path:
    from transformers import MarianTokenizer

    from models.verify import load_sentences

    tok = MarianTokenizer.from_pretrained(str(ONNX_DIR))
    model = OnnxMarian(ONNX_DIR)
    items = []
    for text in load_sentences():
        src = tok(text, truncation=True, max_length=MAX_SRC)["input_ids"]
        out = model.greedy(src)
        items.append({"text": text, "src_ids": src, "out_ids": out, "out_text": tok.decode(out, skip_special_tokens=True)})
    path = OUT / "golden_opus.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def write_tokenizer_cases() -> Path:
    from transformers import MarianTokenizer

    tok = MarianTokenizer.from_pretrained(str(ONNX_DIR))
    items = [{"text": t, "src_ids": tok(t, truncation=True, max_length=MAX_SRC)["input_ids"]} for t in TOKENIZER_CASES]
    path = OUT / "golden_tokenizer.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


if __name__ == "__main__":
    if sys.argv[1:] == ["golden"]:
        print(f"Wrote {write_golden()}")
        print(f"Wrote {write_tokenizer_cases()}")
    else:
        print(__doc__)
