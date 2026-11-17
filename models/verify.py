"""Compare converted models (CT2) with the original transformers model.

Usage:
  python -m models.verify ct2 <key> [--beam N]
Heavy libraries are imported inside functions so the pure helpers stay testable on CI.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from models.registry import MODELS, ModelSpec

ROOT = Path(__file__).parent
OUT = ROOT / "out"
MAX_LEN = 256


def strip_prefix(tokens: list[str], prefix: str | None) -> list[str]:
    if prefix is None:
        return list(tokens)
    i = 0
    while i < len(tokens) and tokens[i] == prefix:
        i += 1
    return list(tokens[i:])


def leaked_lang_tokens(tokens: list[str], prefix: str | None) -> int:
    """Language tokens left in a raw hypothesis after the forced prefix (decode() would hide them)."""
    if prefix is None:
        return 0
    return strip_prefix(tokens, prefix).count(prefix)


def agreement(ref: list[str], hyp: list[str]) -> float:
    def norm(s: str) -> str:
        return " ".join(s.split())

    same = sum(norm(a) == norm(b) for a, b in zip(ref, hyp))
    return same / len(ref) if ref else 1.0


def load_sentences() -> list[str]:
    lines = (ROOT / "sentences_en.txt").read_text(encoding="utf-8").splitlines()
    return [s for s in lines if s.strip()]


def load_tokenizer(spec: ModelSpec, path: str | Path | None = None):
    from transformers import AutoTokenizer

    kwargs = {"src_lang": spec.src_lang} if spec.src_lang else {}
    return AutoTokenizer.from_pretrained(str(path or spec.hf_id), **kwargs)


def reference_translate(spec: ModelSpec, texts: list[str]) -> list[str]:
    import torch
    from transformers import AutoModelForSeq2SeqLM

    tok = load_tokenizer(spec)
    model = AutoModelForSeq2SeqLM.from_pretrained(spec.hf_id).eval()
    gen = {"num_beams": 1, "max_new_tokens": MAX_LEN}
    if spec.tgt_prefix:
        gen["decoder_start_token_id"] = tok.convert_tokens_to_ids(spec.tgt_prefix)
    outs = []
    with torch.no_grad():
        for text in texts:
            ids = tok(text, return_tensors="pt")
            out = model.generate(**ids, **gen)
            outs.append(tok.decode(out[0], skip_special_tokens=True))
    return outs


def _dir_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def _new_translator(model_dir: Path):
    import ctranslate2

    return ctranslate2.Translator(
        str(model_dir), device="cpu", compute_type="int8", intra_threads=2, inter_threads=1
    )


def ct2_translate(spec: ModelSpec, model_dir: Path, texts: list[str], beam: int, translator=None, tok=None, leaks: list[int] | None = None) -> list[str]:
    tok = tok or load_tokenizer(spec, model_dir)
    translator = translator or _new_translator(model_dir)
    src = [tok.convert_ids_to_tokens(tok.encode(t)) for t in texts]
    kwargs = {"beam_size": beam, "max_decoding_length": MAX_LEN}
    if spec.tgt_prefix:
        kwargs["target_prefix"] = [[spec.tgt_prefix]] * len(texts)
    results = translator.translate_batch(src, **kwargs)
    outs = []
    for r in results:
        raw = r.hypotheses[0]
        tokens = strip_prefix(raw, spec.tgt_prefix)
        outs.append(tok.decode(tok.convert_tokens_to_ids(tokens), skip_special_tokens=True))
        if leaks is not None:
            # CT2 forces target_prefix and does not echo it, so only count lang tokens that remain
            leaks.append(leaked_lang_tokens(raw, spec.tgt_prefix))
    return outs


def verify_ct2(key: str, beam: int) -> dict:
    import psutil
    import sacrebleu

    spec = MODELS[key]
    model_dir = OUT / f"{key}-ct2"
    texts = load_sentences()
    proc = psutil.Process()
    tok = load_tokenizer(spec, model_dir)
    rss0 = proc.memory_info().rss
    t0 = time.perf_counter()
    translator = _new_translator(model_dir)
    load_ms = (time.perf_counter() - t0) * 1000
    rss_mb = (proc.memory_info().rss - rss0) / 1e6

    leaks: list[int] = []
    greedy = ct2_translate(spec, model_dir, texts, 1, translator, tok, leaks)
    ref = reference_translate(spec, texts)
    chrf = [sacrebleu.sentence_chrf(h, [r]).score for h, r in zip(greedy, ref)]
    # raw-token check (decode() with skip_special_tokens would hide them)
    bad_lang = [t for t, n in zip(texts, leaks) if n]
    empty = [t for t, h in zip(texts, greedy) if not h.strip()]

    ct2_translate(spec, model_dir, texts[:2], beam, translator, tok)  # warm-up
    per_sentence = []
    for t in texts:
        s = time.perf_counter()
        ct2_translate(spec, model_dir, [t], beam, translator, tok)
        per_sentence.append((time.perf_counter() - s) * 1000)
    batch, words = [], 0
    for t in texts:  # ~50-word batch
        if words >= 50:
            break
        batch.append(t)
        words += len(t.split())
    s = time.perf_counter()
    beam_out = ct2_translate(spec, model_dir, batch, beam, translator, tok)
    batch_ms = (time.perf_counter() - s) * 1000

    ps = sorted(per_sentence)
    report = {
        "model": key,
        "beam": beam,
        "exact_agreement_greedy": round(agreement(ref, greedy), 3),
        "chrf_vs_transformers_mean": round(statistics.mean(chrf), 2),
        "chrf_min": round(min(chrf), 2),
        "outputs_with_lang_token": bad_lang,
        "empty_outputs": empty,
        "load_ms": round(load_ms),
        "ram_mb_after_load": round(rss_mb),
        "size_mb": round(_dir_size_mb(model_dir)),
        "ms_per_sentence_median": round(statistics.median(ps), 1),
        "ms_per_sentence_p95": round(ps[max(0, int(len(ps) * 0.95) - 1)], 1),
        "batch_words": words,
        "batch_ms": round(batch_ms, 1),
        "samples": [
            {"en": t, "ref": r, "ct2_greedy": g, "ct2_beam": b}
            for t, r, g, b in zip(batch, ref, greedy, beam_out)
        ],
        "all": [{"en": t, "ref": r, "ct2_greedy": g} for t, r, g in zip(texts, ref, greedy)],
    }
    (OUT / f"verify_{key}_ct2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("backend", choices=["ct2"])
    ap.add_argument("key", choices=list(MODELS))
    ap.add_argument("--beam", type=int, default=2)
    args = ap.parse_args()
    report = verify_ct2(args.key, args.beam)
    print(json.dumps({k: v for k, v in report.items() if k not in ("samples", "all")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
