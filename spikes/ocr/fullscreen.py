"""Spike A (full-screen mode): OCR whole screenshots, check every expected line is found.

Usage: .venv\\Scripts\\python -m spikes.ocr.fullscreen
Reads spikes/ocr/data/full/*.jpg|png with a same-name .txt: one expected line per line.
"""
import json
import statistics
import time
from pathlib import Path

from PIL import Image

from spikes.ocr import engines
from spikes.ocr.metrics import cer

DATA = Path(__file__).parent / "data" / "full"
OUT = Path(__file__).parents[1] / "out" / "ocr_fullscreen.json"
ENGINES = {"windows": engines.windows_ocr, "rapid": engines.rapid_ocr}
FOUND = 0.1  # a line counts as found when its CER is at most this


def _norm(s: str) -> str:
    return " ".join(s.split())


def line_match(expected: list[str], got: list[str]) -> list[tuple[str, str, float]]:
    """For each expected line: the best OCR line and its CER (0 when contained in a longer line)."""
    out = []
    for exp in expected:
        best, best_cer = "", 1.0
        for g in got:
            c = 0.0 if _norm(exp) in _norm(g) else cer(exp, g)
            if c < best_cer:
                best, best_cer = g, c
        out.append((exp, best, best_cer))
    return out


def main() -> None:
    images = sorted([*DATA.glob("*.jpg"), *DATA.glob("*.png")])
    report = []
    for img_path in images:
        expected = [l for l in img_path.with_suffix(".txt").read_text(encoding="utf-8").splitlines() if l.strip()]
        img = Image.open(img_path)
        for name, fn in ENGINES.items():
            fn(img)  # warm-up
            times, text = [], ""
            for _ in range(3):
                t0 = time.perf_counter()
                text = fn(img)
                times.append((time.perf_counter() - t0) * 1000)
            lines = [l for l in text.splitlines() if l.strip()]
            matches = line_match(expected, lines)
            report.append({
                "image": img_path.name, "engine": name, "ms": round(statistics.median(times)),
                "found": sum(c <= FOUND for *_, c in matches), "expected": len(expected),
                "mean_cer": round(statistics.mean(c for *_, c in matches), 3),
                "misses": [(e, g, round(c, 3)) for e, g, c in matches if c > 0],
                "ocr_lines": lines,
            })
    print(f"{'image':16} {'engine':8} {'found':>7} {'meanCER':>8} {'ms':>6}")
    for r in report:
        print(f"{r['image'][:16]:16} {r['engine']:8} {r['found']:>3}/{r['expected']:<3} {r['mean_cer']:8.3f} {r['ms']:6}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
