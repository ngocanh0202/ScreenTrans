"""Private training data from an LLM, with YOUR OWN key (Phase 6). The result is for your own model only:
the providers' terms do not allow using their output to build competing models, so never publish it and never put
it in the repo.

    .venv\\Scripts\\python -m training.distill_data --engine gemini --sentences lines.txt --out D:\\my-data
    (prints an estimate; add --yes to run)

Sentences: one per line (--sentences, several files allowed) plus, with --from-log, the English lines the app logged
(translations.jsonl); --with-corrections adds your own fixes (corrections.jsonl) as pairs. Output: OUT/distilled.tsv
(en<TAB>vi), appended, resumable. The key comes from the app's key store (Cài đặt → Dịch bằng) or SCREENTRANS_KEY;
it is never written anywhere.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "windows"))

from app.translate.llm_prompt import build_messages, parse_reply  # noqa: E402
from app.translate.remote import NAMES, RemoteError, make_client  # noqa: E402

CHARS_PER_TOKEN = 4  # rough: estimates only


def _default_data_dir() -> Path:
    from app.config import _default_data_dir

    return Path(_default_data_dir())


def _key(engine: str, data_dir: Path) -> str:
    key = os.environ.get("SCREENTRANS_KEY", "")
    if key:
        return key
    from app.secrets import KeyStore

    return KeyStore(data_dir).get(engine)


def _sources(args, data_dir: Path) -> list[str]:
    out: list[str] = []
    for f in args.sentences or []:
        out += [l.strip() for l in Path(f).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.from_log:
        log = data_dir / "translations.jsonl"
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(line)["source"].strip())
                except (ValueError, KeyError, AttributeError):
                    continue
    return list(dict.fromkeys(s for s in out if s))


def _corrections(data_dir: Path) -> list[tuple[str, str]]:
    path = data_dir / "corrections.jsonl"
    pairs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                pairs.append((row["source"].strip(), row["corrected"].strip()))
            except (ValueError, KeyError, AttributeError):
                continue
    return [(s, t) for s, t in pairs if s and t]


def _clean(s: str) -> str:
    return " ".join(s.replace("\t", " ").split())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", required=True, choices=sorted(NAMES))
    ap.add_argument("--model", default="", help="model name (default: the app's default for the engine)")
    ap.add_argument("--url", default="", help="Kaggle server URL")
    ap.add_argument("--sentences", nargs="*", help="files with one English sentence per line")
    ap.add_argument("--from-log", action="store_true", help="add the English lines the app logged (translations.jsonl)")
    ap.add_argument("--with-corrections", action="store_true", help="add your own fixes (corrections.jsonl) as pairs")
    ap.add_argument("--data-dir", type=Path, default=None, help="the app's data folder (default: %%LOCALAPPDATA%%/ScreenTrans)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="at most this many new sentences")
    ap.add_argument("--budget-chars", type=int, default=0, help="stop once this many characters were sent")
    ap.add_argument("--yes", action="store_true", help="really send (without it: only the estimate)")
    args = ap.parse_args(argv)

    data_dir = args.data_dir or _default_data_dir()
    out_file = args.out / "distilled.tsv"
    args.out.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_file.exists():
        done = {l.split("\t", 1)[0] for l in out_file.read_text(encoding="utf-8").splitlines() if "\t" in l}
    todo = [s for s in _sources(args, data_dir) if _clean(s) not in done]
    if args.limit:
        todo = todo[: args.limit]
    chars = sum(len(s) for s in todo)
    print(f"{len(todo)} sentences to translate ({chars} characters; ~{chars * 3 // CHARS_PER_TOKEN} tokens in + out, "
          f"plus the prompt per batch of {args.batch}). Already done: {len(done)}.")
    if args.with_corrections:
        fixes = [(s, t) for s, t in _corrections(data_dir) if _clean(s) not in done]
        with out_file.open("a", encoding="utf-8") as f:
            for s, t in fixes:
                f.write(f"{_clean(s)}\t{_clean(t)}\n")
                done.add(_clean(s))
        print(f"added {len(fixes)} of your own corrections")
    if not args.yes:
        print("Nothing sent. Run again with --yes to translate (your provider bills you).")
        return 1
    key = _key(args.engine, data_dir)
    if not key:
        print(f"No key for {NAMES[args.engine]}: enter it in the app (Cài đặt → Dịch bằng) or set SCREENTRANS_KEY.")
        return 2
    client = make_client(args.engine, key, model=args.model, url=args.url)
    sent = written = 0
    with out_file.open("a", encoding="utf-8") as f:
        for i in range(0, len(todo), args.batch):
            if args.budget_chars and sent >= args.budget_chars:
                print(f"budget of {args.budget_chars} characters reached")
                break
            batch = todo[i:i + args.batch]
            system, user = build_messages(batch, [], None, {})
            try:
                reply = client.complete(system, user, 60.0)
            except RemoteError as e:
                print(f"stopped: {e}")  # the message never holds the key
                break
            sent += sum(len(s) for s in batch)
            out = parse_reply(reply, len(batch))
            if out is None:
                print(f"batch {i // args.batch + 1}: unusable reply, skipped")
                continue
            for s, t in zip(batch, out):
                f.write(f"{_clean(s)}\t{_clean(t)}\n")
                written += 1
            f.flush()
    print(f"wrote {written} pairs to {out_file} ({sent} characters sent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
