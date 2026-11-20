"""Does OpenCV preprocessing help Windows OCR on game text? (experiment, 2026-11-20)

Variants of the image before Windows OCR, measured on:
- crops  (spikes/ocr/data/rv_*.png + .txt): character error rate (CER) of the whole text;
- full   (spikes/ocr/data/full/*.jpg + .txt): expected lines found (CER <= 0.1) on whole screenshots;
- hard   (--hard DIR: *.png/*.jpg + .txt): the same on hard screens (blurred typewriter text, busy scenes).

    .venv\\Scripts\\python -m spikes.ocr.preprocess [--hard DIR]
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "windows"))

from app.ocr.windows_ocr import WindowsOcr  # noqa: E402
from spikes.ocr.fullscreen import FOUND, line_match  # noqa: E402
from spikes.ocr.metrics import cer  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"


def _bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _pil(a: np.ndarray) -> Image.Image:
    if a.ndim == 2:
        return Image.fromarray(a)
    return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))


def none(img):
    return img


def upscale2(img):
    a = _bgr(img)
    return _pil(cv2.resize(a, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))


def clahe(img):
    g = cv2.cvtColor(_bgr(img), cv2.COLOR_BGR2GRAY)
    return _pil(cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g))


def upscale2_sharpen(img):
    a = cv2.resize(_bgr(img), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(a, (0, 0), 2.0)
    return _pil(cv2.addWeighted(a, 1.6, blur, -0.6, 0))


def upscale2_otsu(img):
    g = cv2.cvtColor(cv2.resize(_bgr(img), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2GRAY)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if b.mean() < 127:  # keep dark text on light, like a page
        b = 255 - b
    return _pil(b)


def upscale2_clahe_sharpen(img):
    a = cv2.resize(_bgr(img), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY))
    blur = cv2.GaussianBlur(g, (0, 0), 2.0)
    return _pil(cv2.addWeighted(g, 1.6, blur, -0.6, 0))


VARIANTS = {"none": none, "up2": upscale2, "clahe": clahe, "up2+sharp": upscale2_sharpen,
            "up2+otsu": upscale2_otsu, "up2+clahe+sharp": upscale2_clahe_sharpen}


def run(ocr, fn, img) -> tuple[list[str], float]:
    t0 = time.perf_counter()
    prepared = fn(img)
    lines = [l.text for l in ocr.recognize(prepared)]
    return lines, (time.perf_counter() - t0) * 1000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hard", type=Path, help="folder of hard screenshots with expected lines (.txt)")
    args = ap.parse_args()
    ocr = WindowsOcr()
    crops = sorted(DATA.glob("rv_*.png"))
    fulls = sorted((DATA / "full").glob("*.jpg"))
    hards = sorted([*args.hard.glob("*.png"), *args.hard.glob("*.jpg")]) if args.hard else []
    print(f"{'variant':18} {'crops CER':>9} {'full found':>11} {'hard found':>11} {'ms/full':>8}")
    for name, fn in VARIANTS.items():
        c = []
        for p in crops:
            lines, _ = run(ocr, fn, Image.open(p))
            c.append(cer(p.with_suffix(".txt").read_text(encoding="utf-8"), " ".join(lines)))
        found = total = 0
        ms = []
        for p in fulls:
            exp = [l for l in p.with_suffix(".txt").read_text(encoding="utf-8").splitlines() if l.strip()]
            lines, t = run(ocr, fn, Image.open(p))
            ms.append(t)
            found += sum(x <= FOUND for *_, x in line_match(exp, lines))
            total += len(exp)
        hfound = htotal = 0
        for p in hards:
            exp = [l for l in p.with_suffix(".txt").read_text(encoding="utf-8").splitlines() if l.strip()]
            lines, _ = run(ocr, fn, Image.open(p))
            hfound += sum(x <= FOUND for *_, x in line_match(exp, lines))
            htotal += len(exp)
        hard = f"{hfound}/{htotal}" if hards else "-"
        print(f"{name:18} {statistics.mean(c):9.3f} {found:>5}/{total:<5} {hard:>11} {statistics.median(ms):8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
