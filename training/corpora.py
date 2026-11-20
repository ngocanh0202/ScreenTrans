"""Openly licensed EN-VI corpora for the public fine-tuned model (Phase 6) and the dataset builder.

Only corpora allowed for training AND publishing a derived model (docs/superpowers/reports/2026-11-20-en-vi-licenses.md).
Downloads happen on Kaggle; tests inject fake downloads.
"""
import json
import random
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from training.filters import dedupe, keep_pair, split_heldout

OPUS_API = "https://opus.nlpl.eu/opusapi/"


@dataclass(frozen=True)
class Corpus:
    name: str          # OPUS corpus id
    license: str
    attribution: str
    max_pairs: int     # kept pairs (after filtering) taken from this corpus
    enabled: bool = True
    share_alike: bool = False


CORPORA = [
    Corpus("ALT", "CC BY 4.0", "Asian Language Treebank, NICT (Riza et al., 2016)", 20_000),
    Corpus("Tatoeba", "CC BY 2.0 FR", "Tatoeba (tatoeba.org) contributors", 20_000),
    Corpus("translatewiki", "CC BY 3.0", "translatewiki.net contributors", 50_000),
    Corpus("ELRC_2922", "CC BY 4.0", "ELRC (European Language Resource Coordination)", 5_000),
    Corpus("NLLB", "ODC-By 1.0", "NLLB mined data, Meta AI / AllenAI, via OPUS (sources keep their own terms)", 600_000),
    Corpus("ParaCrawl-Bonus", "CC0 (packaging)", "ParaCrawl project, via OPUS (texts are web-crawled)", 300_000),
    Corpus("WikiMatrix", "CC BY-SA 4.0", "WikiMatrix (Schwenk et al., 2019), via OPUS", 300_000, enabled=False,
           share_alike=True),
]


def resolve_url(corpus: Corpus, fetch_json: Callable[[str], dict]) -> str:
    """The latest en-vi moses zip of the corpus, asked from the OPUS API."""
    q = urllib.parse.urlencode({"source": "en", "target": "vi", "corpus": corpus.name,
                                "preprocessing": "moses", "version": "latest"})
    data = fetch_json(f"{OPUS_API}?{q}")
    return data["corpora"][0]["url"]


def read_moses_zip(path: Path) -> Iterator[tuple[str, str]]:
    """Line-aligned (en, vi) pairs from an OPUS moses zip; BOM / CR removed; a line-count mismatch stops it."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        en_name = next(n for n in names if n.endswith(".en"))
        vi_name = next(n for n in names if n.endswith(".vi"))
        with z.open(en_name) as fe, z.open(vi_name) as fv:
            while True:
                le, lv = fe.readline(), fv.readline()
                if not le and not lv:
                    return
                if not le or not lv:
                    print(f"{Path(path).name}: line count mismatch between {en_name} and {vi_name}; stopped there")
                    return
                yield (le.decode("utf-8", "replace").replace("﻿", "").rstrip("\r\n"),
                       lv.decode("utf-8", "replace").replace("﻿", "").rstrip("\r\n"))


def _tsv(s: str) -> str:
    return s.replace("\t", " ")


def build(out_dir: Path, corpora: list[Corpus], download: Callable[[Corpus, Path], Path],
          heldout: set[str] = frozenset(), seed: int = 13, dev_fraction: float = 0.01, dev_max: int = 2000) -> dict:
    """train.tsv / dev.tsv (en<TAB>vi), DATA_LICENSES.md and stats.json in out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs: list[tuple[str, str]] = []
    stats: dict = {}
    for c in corpora:
        try:
            path = download(c, out_dir / f"{c.name}.zip")
        except Exception as e:  # one unavailable corpus must not stop the build
            print(f"{c.name}: download failed ({e}); skipped")
            stats[c.name] = {"read": 0, "kept": 0, "error": str(e)}
            continue
        read = kept = 0
        for en, vi in read_moses_zip(path):
            read += 1
            if keep_pair(en, vi):
                pairs.append((en, vi))
                kept += 1
                if kept >= c.max_pairs:
                    break
        stats[c.name] = {"read": read, "kept": kept}
        print(f"{c.name}: {kept} of {read} pairs kept")
    pairs = split_heldout(dedupe(pairs), heldout)
    random.Random(seed).shuffle(pairs)
    n_dev = min(dev_max, max(1, int(len(pairs) * dev_fraction))) if pairs else 0
    dev, train = pairs[:n_dev], pairs[n_dev:]
    for name, rows in (("train.tsv", train), ("dev.tsv", dev)):
        (out_dir / name).write_text("".join(f"{_tsv(e)}\t{_tsv(v)}\n" for e, v in rows), encoding="utf-8")
    lines = ["# Training data licenses", "", "| Corpus | License | Attribution | Pairs kept |", "|---|---|---|---|"]
    lines += [f"| {c.name} | {c.license} | {c.attribution} | {stats.get(c.name, {}).get('kept', 0)} |" for c in corpora]
    if any(c.share_alike for c in corpora):
        lines += ["", "Share-alike data was used: publish this model under CC BY-SA 4.0."]
    (out_dir / "DATA_LICENSES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    stats["total"] = len(pairs)
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return stats
