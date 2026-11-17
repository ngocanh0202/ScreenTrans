"""Per-step latency of the Windows pipeline on real screenshots.

Usage (from the repo root):
  .venv\\Scripts\\python windows/scripts/benchmark.py --model-dir models/out/vinai-en2vi-ct2
"""
import argparse
import glob
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "windows"))

from PIL import Image  # noqa: E402

from app.cache import TranslationCache  # noqa: E402
from app.glossary import COMMON_GLOSSARY, Glossary  # noqa: E402
from app.ocr.windows_ocr import WindowsOcr  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from app.translate.ct2 import Ct2Translator  # noqa: E402

LIVE_BUDGET_MS = 400  # AGENT.md §13: Live, text settled -> translation shown (1-2 sentences)
STEPS = ("ocr", "postprocess", "translate", "total")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--images", default=str(ROOT / "spikes" / "ocr" / "data" / "rv_*.png"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--beam", type=int, default=2)
    args = ap.parse_args()

    t0 = time.perf_counter()
    translator = Ct2Translator(args.model_dir, beam_size=args.beam)
    load_ms = (time.perf_counter() - t0) * 1000
    warm_ms = translator.warm_up()
    glossary = Glossary.load(ROOT / "shared" / "glossary" / "games" / "reverse1999.json", COMMON_GLOSSARY)
    pipeline = Pipeline(WindowsOcr(), translator, glossary, TranslationCache(1, None))
    print(f"model {translator.model_id}  beam {args.beam}  load {load_ms:.0f} ms  warm-up {warm_ms:.0f} ms")

    rows = []
    for path in sorted(glob.glob(args.images)):
        img = Image.open(path)
        runs = []
        for _ in range(args.runs):
            pipeline.cache = TranslationCache(1000, None)  # no cache hits between runs
            result = pipeline.run(img)
            runs.append(result.timings_ms)
        sentences = sum(len(s.source.split(". ")) for s in result.segments if s.kind == "text")
        med = {k: statistics.median(r[k] for r in runs) for k in STEPS}
        rows.append({"image": Path(path).name, "sentences": sentences, **{k: round(v, 1) for k, v in med.items()}})

    print(f"{'image':24} {'sent':>4} " + " ".join(f"{k:>11}" for k in STEPS))
    for r in rows:
        print(f"{r['image']:24} {r['sentences']:>4} " + " ".join(f"{r[k]:>9.0f}ms" for k in STEPS))
    short = [r for r in rows if r["sentences"] <= 2]
    if short:
        worst = max(r["total"] for r in short)
        verdict = "OK" if worst < LIVE_BUDGET_MS else "OVER"
        print(f"Live budget (1-2 sentences) < {LIVE_BUDGET_MS} ms: worst {worst:.0f} ms -> {verdict}")
    out = ROOT / "windows" / "out" / f"benchmark_{translator.model_id}_beam{args.beam}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": translator.model_id, "beam": args.beam, "load_ms": round(load_ms),
                               "warm_up_ms": round(warm_ms), "images": rows}, indent=1), encoding="utf-8")
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
