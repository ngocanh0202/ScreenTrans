"""Speed / quality of the on-device models with different settings (Phase 5: tune the defaults on real lines).

For each CTranslate2 model folder and each beam size x thread count: the time per sentence (one sentence per call,
like Live) and per batch (every sentence of one OCR read in one call), plus the translations of each beam size side
by side for you to judge. Sentences: the logged dialogue lines (translations.jsonl), --sentences FILE, built-in
samples. Nothing is downloaded: it uses models already on this PC.

    .venv\\Scripts\\python windows/scripts/bench_models.py
    .venv\\Scripts\\python windows/scripts/bench_models.py --model D:\\models\\screentrans-en-vi-ct2 --limit 30

Writes windows/out/bench_models.html (+ .json).
"""
import argparse
import html
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "windows"))
sys.path.insert(0, str(ROOT / "windows" / "scripts"))

from compare_engines import SAMPLES, logged_sentences  # noqa: E402

BEAMS = (1, 2, 4)
THREADS = (1, 2, 4)


def default_models() -> list[Path]:
    """models/out exports and the app's downloaded models (data_dir/models/<id>/<version>)."""
    out = [d for d in (ROOT / "models" / "out").glob("*-ct2") if (d / "model.bin").is_file()]
    data = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ScreenTrans" / "models"
    out += [d for d in data.glob("*/*") if (d / "model.bin").is_file()]
    return out


def bench(model_dir: Path, sentences: list[str], beams=BEAMS, threads=THREADS, make=None) -> dict:
    """{"speed": [{beam, threads, ms_sentence, ms_batch}], "outputs": {beam: [translations]}}."""
    if make is None:
        from app.translate.ct2 import Ct2Translator as make
    speed, outputs = [], {}
    for t in threads:
        for b in beams:
            tr = make(model_dir, beam_size=b, intra_threads=t)
            tr.translate(["Hello."])  # warm up
            per = []
            outs = []
            for s in sentences:
                t0 = time.perf_counter()
                outs.append(tr.translate([s])[0])
                per.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            tr.translate(sentences)
            batch = (time.perf_counter() - t0) * 1000 / max(1, len(sentences))
            speed.append({"beam": b, "threads": t, "ms_sentence": statistics.median(per) if per else 0.0,
                          "ms_batch": batch})
            outputs.setdefault(b, outs)
            print(f"  {model_dir.name} beam={b} threads={t}: {speed[-1]['ms_sentence']:.0f} ms/sentence "
                  f"(batch {batch:.0f} ms/sentence)", flush=True)
    return {"speed": speed, "outputs": outputs}


def write_html(path: Path, sentences: list[str], results: dict) -> None:
    parts = ["<!doctype html><meta charset='utf-8'><title>Đo model</title><style>body{font:15px Segoe UI,sans-serif;"
             "margin:16px}table{border-collapse:collapse;margin-bottom:24px}td,th{border:1px solid #ccc;padding:5px 8px;"
             "vertical-align:top;text-align:left}th{background:#f3f3f3}.src{color:#555}</style>",
             "<h2>Tốc độ và chất lượng model trên máy</h2><p>ms/câu: trung vị khi dịch từng câu (như Live); "
             "lô: mọi câu trong một lần gọi. Số luồng không đổi bản dịch, chỉ đổi tốc độ.</p>"]
    for name, r in results.items():
        parts.append(f"<h3>{html.escape(name)}</h3><table><tr><th>beam</th><th>luồng</th><th>ms/câu</th>"
                     "<th>lô ms/câu</th></tr>")
        for row in r["speed"]:
            parts.append(f"<tr><td>{row['beam']}</td><td>{row['threads']}</td><td>{row['ms_sentence']:.0f}</td>"
                         f"<td>{row['ms_batch']:.0f}</td></tr>")
        parts.append("</table>")
        beams = sorted(r["outputs"])
        parts.append("<table><tr><th>Câu gốc</th>" + "".join(f"<th>beam {b}</th>" for b in beams) + "</tr>")
        for i, s in enumerate(sentences):
            parts.append(f"<tr><td class=src>{html.escape(s)}</td>"
                         + "".join(f"<td>{html.escape(r['outputs'][b][i])}</td>" for b in beams) + "</tr>")
        parts.append("</table>")
    path.write_text("".join(parts), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, action="append", help="a CTranslate2 model folder (repeatable)")
    ap.add_argument("--sentences", type=Path, help="extra sentences, one per line")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--out", type=Path, default=ROOT / "windows" / "out" / "bench_models.html")
    args = ap.parse_args(argv)
    sentences = logged_sentences()
    if args.sentences:
        sentences += [l.strip() for l in args.sentences.read_text(encoding="utf-8").splitlines() if l.strip()]
    sentences = list(dict.fromkeys(sentences + SAMPLES))[: args.limit]
    models = args.model or default_models()
    if not models:
        print("No CTranslate2 model found: pass --model <folder>.")
        return 1
    results = {}
    for m in models:
        results[f"{m.parent.name}/{m.name}" if m.parent.name != "out" else m.name] = bench(m, sentences)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_html(args.out, sentences, results)
    args.out.with_suffix(".json").write_text(json.dumps({"sentences": sentences, "results": results},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
