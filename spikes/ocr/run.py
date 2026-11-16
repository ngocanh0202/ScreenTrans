"""Spike A: compare Windows OCR and RapidOCR on game screenshots.

Usage: .venv\Scripts\python -m spikes.ocr.run
Reads spikes/ocr/data/*.png with a same-name .txt holding the true text.
"""
import json
import statistics
import time
from pathlib import Path

from PIL import Image

from spikes.ocr import engines
from spikes.ocr.metrics import cer

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parents[1] / "out" / "ocr_results.json"
ENGINES = {"windows": engines.windows_ocr, "rapid": engines.rapid_ocr}
RUNS = 5


def measure(fn, img):
    fn(img)  # warm-up, not timed
    times, text = [], ""
    for _ in range(RUNS):
        t0 = time.perf_counter()
        text = fn(img)
        times.append((time.perf_counter() - t0) * 1000)
    return text, statistics.median(times)


def main() -> None:
    images = sorted(DATA.glob("*.png"))
    if not images:
        print(f"No images in {DATA}. See {DATA / 'README.md'}.")
        return
    rows = []
    for png in images:
        ref = png.with_suffix(".txt").read_text(encoding="utf-8")
        img = Image.open(png)
        for name, fn in ENGINES.items():
            try:
                hyp, ms = measure(fn, img)
            except engines.OcrEngineUnavailable as e:
                print(f"[{name}] {e}")
                continue
            rows.append({"image": png.name, "engine": name, "cer": round(cer(ref, hyp), 4), "ms": round(ms, 1), "text": hyp})
    print(f"{'image':30} {'engine':8} {'CER':>6} {'ms':>7}")
    for r in rows:
        print(f"{r['image']:30} {r['engine']:8} {r['cer']:6.3f} {r['ms']:7.1f}")
    for name in ENGINES:
        sub = [r for r in rows if r["engine"] == name]
        if sub:
            print(f"MEAN {name:8} CER {statistics.mean(r['cer'] for r in sub):.3f}  ms {statistics.median(r['ms'] for r in sub):.1f}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
