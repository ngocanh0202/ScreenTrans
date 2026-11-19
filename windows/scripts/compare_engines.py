"""Compare EN->VI translations side by side: vinai (CT2), opus-mt (CT2) and Lingva (a Google Translate front-end).

Sentences: the dialogue lines in %LOCALAPPDATA%/ScreenTrans/translations.jsonl (non-sentences such as desktop
icon labels are skipped), plus --sentences FILE (one per line), plus built-in game-like samples
(--no-samples to skip). Lingva sends every sentence over the network to the chosen instance (and Google).

    .venv\\Scripts\\python windows/scripts/compare_engines.py
    .venv\\Scripts\\python windows/scripts/compare_engines.py --sentences my_lines.txt --lingva https://lingva.ml

Writes windows/out/compare_engines.html (+ .json) and prints the average time per sentence.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "windows"))

LINGVA_INSTANCES = ["https://lingva.ml", "https://lingva.lunar.icu", "https://translate.plausibility.cloud"]

# Original lines written for this comparison (no game text): dialogue, UI, idioms, names, long sentences.
SAMPLES = [
    "Where are you going? The station is closed today.",
    "I told you not to touch that, didn't I?",
    "We have to leave before the storm reaches the harbor.",
    "Don't worry about me. I'll catch up with you later.",
    "Your inventory is full. Discard an item to continue.",
    "Are you sure you want to overwrite this save file?",
    "The old clockmaker hasn't opened his shop in years.",
    "That's easier said than done.",
    "Hold your horses, we're not there yet!",
    "If you hadn't come back for me, I would have been lost forever.",
    "She smiled, but her eyes told a different story.",
    "Press any key to start.",
    "Quest completed: Return the lost letter to the innkeeper.",
    "It's raining cats and dogs out there.",
    "I owe you one.",
    "Let's call it a day.",
    "The ritual must be finished before the clock strikes midnight, or everything we have done will be for nothing.",
    "Who goes there? State your name and business.",
    "You can't judge a book by its cover.",
    "Equip the silver ring to increase your resistance to curses.",
    "He's been acting strange ever since he came back from the north.",
    "Wait... did you hear that?",
    "Thanks, but I can manage on my own.",
    "The bridge collapsed, so we'll have to take the long way around.",
    "Level up! Your attack has increased by five.",
]


def is_sentence(s: str) -> bool:
    s = s.strip()
    return len(s.split()) >= 4 and bool(re.search(r"[.!?…][\"'”’)]*$", s))


def logged_sentences() -> list[str]:
    path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ScreenTrans" / "translations.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line)["source"])
        except (ValueError, KeyError, TypeError):
            continue
    return [s for s in out if is_sentence(s)]


def ct2_engine(model_dir: Path):
    from app.translate.ct2 import Ct2Translator

    tr = Ct2Translator(model_dir, beam_size=2, intra_threads=2)
    tr.translate(["Hello."])  # warm up
    return lambda s: tr.translate([s])[0]


def lingva_engine(instances: list[str], timeout: float):
    state = {"base": None}

    def call(base: str, s: str) -> str:
        url = f"{base.rstrip('/')}/api/v1/en/vi/{urllib.parse.quote(s, safe='')}"
        req = urllib.request.Request(url, headers={"User-Agent": "ScreenTrans-compare/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))["translation"]

    def translate(s: str) -> str:
        order = [state["base"]] if state["base"] else []
        order += [b for b in instances if b != state["base"]]
        errors = []
        for base in order:
            try:
                out = call(base, s)
                state["base"] = base
                return out
            except Exception as e:  # noqa: BLE001 - try the next instance
                errors.append(f"{base}: {e}")
        raise RuntimeError("; ".join(errors))

    return translate, state


from app.config import _default_data_dir  # noqa: E402


def remote_engine(engine: str, data_dir: Path, model: str, url: str, timeout: float, dry_run: bool):
    """A remote LLM (Phase 5) with the app's prompt: each sentence with the 3 before it as context."""
    from app.secrets import KeyStore
    from app.translate.llm_prompt import build_messages, parse_reply
    from app.translate.remote import DEFAULT_MODELS, RemoteError, make_client

    model = model or DEFAULT_MODELS[engine]
    client = None if dry_run else make_client(engine, KeyStore(data_dir).get(engine), model=model, url=url)
    seen: list[str] = []

    def translate(s: str) -> str:
        system, user = build_messages([s], seen[-3:], None, {})
        seen.append(s)
        if client is None:
            print(f"--- {engine} ({model})\n{system}\n\n{user}\n")
            return "(dry run)"
        try:
            out = parse_reply(client.complete(system, user, timeout), 1)
        except RemoteError as e:
            return f"⚠ {e}"
        return out[0] if out else "⚠ trả lời không hợp lệ"

    return translate


def run(name, fn, sentences):
    rows = []
    for s in sentences:
        t0 = time.perf_counter()
        try:
            out = fn(s)
        except Exception as e:  # noqa: BLE001 - shown in the table
            out = f"⚠ {e}"
        rows.append((out, (time.perf_counter() - t0) * 1000))
        print(f"  {name}: {len(rows)}/{len(sentences)}", end="\r", flush=True)
    print()
    return rows


def write_html(path: Path, sentences, results, notes):
    names = list(results)
    avg = {n: sum(ms for _, ms in results[n]) / max(1, len(results[n])) for n in names}
    head = "".join(f"<th>{html.escape(n)}<br><small>{avg[n]:.0f} ms/câu</small></th>" for n in names)
    body = []
    for i, s in enumerate(sentences):
        cells = "".join(f"<td>{html.escape(results[n][i][0])}<br><small>{results[n][i][1]:.0f} ms</small></td>"
                        for n in names)
        body.append(f"<tr><td class=n>{i + 1}</td><td class=src>{html.escape(s)}</td>{cells}</tr>")
    path.write_text(f"""<!doctype html><meta charset="utf-8"><title>So sánh dịch EN→VI</title>
<style>body{{font:15px Segoe UI,sans-serif;margin:16px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}}th{{background:#f3f3f3}}
.src{{color:#555}}.n{{color:#999}}small{{color:#888}}tr:nth-child(even){{background:#fafafa}}</style>
<h2>So sánh dịch Anh → Việt</h2><p>{html.escape(notes)}</p>
<table><tr><th>#</th><th>Câu gốc</th>{head}</tr>{''.join(body)}</table>""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentences", type=Path, help="extra sentences, one per line")
    ap.add_argument("--no-samples", action="store_true", help="only logged / --sentences lines")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--vinai", type=Path, default=ROOT / "models" / "out" / "vinai-en2vi-ct2")
    ap.add_argument("--opus", type=Path, default=ROOT / "models" / "out" / "opus-mt-en-vi-ct2")
    ap.add_argument("--lingva", action="append", help="Lingva instance URL (repeatable); default: public ones")
    ap.add_argument("--no-lingva", action="store_true")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--out", type=Path, default=ROOT / "windows" / "out" / "compare_engines.html")
    ap.add_argument("--engine", action="append", choices=["gemini", "openai", "claude", "kaggle"],
                    help="remote LLM engine (repeatable); key from the app's key store (Cài đặt → Dịch bằng)")
    ap.add_argument("--model", default="", help="model name for --engine (default: the app's default)")
    ap.add_argument("--kaggle-url", default="")
    ap.add_argument("--data-dir", type=Path, default=Path(_default_data_dir()))
    ap.add_argument("--dry-run", action="store_true", help="print the prompts for --engine, no network")
    args = ap.parse_args()

    logged = logged_sentences()
    extra = [l.strip() for l in args.sentences.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if args.sentences else []
    sentences = list(dict.fromkeys(logged + extra + ([] if args.no_samples else SAMPLES)))[: args.limit]
    print(f"{len(sentences)} câu ({len(logged)} câu thoại đã ghi, {len(extra)} từ --sentences)")

    results = {}
    for engine in args.engine or []:
        fn = remote_engine(engine, args.data_dir, args.model, args.kaggle_url, args.timeout, args.dry_run)
        results[f"{engine} (qua mạng)"] = run(engine, fn, sentences)
    if args.dry_run:
        return 0
    for name, d in (("vinai (máy, Windows)", args.vinai), ("opus-mt (máy, Android)", args.opus)):
        if d.exists():
            results[name] = run(name, ct2_engine(d), sentences)
        else:
            print(f"bỏ qua {name}: không có {d}")
    lingva_note = ""
    if not args.no_lingva:
        fn, state = lingva_engine(args.lingva or LINGVA_INSTANCES, args.timeout)
        results["Lingva (Google, qua mạng)"] = run("lingva", fn, sentences)
        lingva_note = f" Lingva: {state['base'] or 'không máy chủ nào trả lời'}."
    args.out.parent.mkdir(parents=True, exist_ok=True)
    notes = (f"{len(sentences)} câu: {len(logged)} câu thoại đã ghi trong translations.jsonl, {len(extra)} câu từ "
             f"--sentences, còn lại là câu mẫu. Dịch thô, không dùng bảng thuật ngữ.{lingva_note}")
    write_html(args.out, sentences, results, notes)
    args.out.with_suffix(".json").write_text(json.dumps(
        {"sentences": sentences, "results": {n: [{"translation": t, "ms": round(ms)} for t, ms in r]
                                            for n, r in results.items()}}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    for n, r in results.items():
        ok = [ms for t, ms in r if not t.startswith("⚠")]
        print(f"{n}: {len(ok)}/{len(r)} câu, trung bình {sum(ok) / max(1, len(ok)):.0f} ms/câu")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
