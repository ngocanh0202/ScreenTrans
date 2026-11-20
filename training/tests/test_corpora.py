"""Corpus catalogue, OPUS reader and dataset builder (fake downloads, no network)."""
import json
import zipfile

from training.corpora import CORPORA, build, read_moses_zip, resolve_url


def fake_zip(path, en_lines, vi_lines, prefix="X.en-vi"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{prefix}.en", "\n".join(en_lines) + "\n")
        z.writestr(f"{prefix}.vi", "\n".join(vi_lines) + "\n")
        z.writestr("README", "x")
    return path


def test_catalogue_has_only_allowed_licenses():
    names = {c.name for c in CORPORA}
    assert {"ALT", "Tatoeba", "translatewiki", "ELRC_2922", "NLLB", "ParaCrawl-Bonus"} <= names
    for banned in ("PhoMT", "TED2020", "QED", "OpenSubtitles", "IWSLT", "MTet"):
        assert banned not in names
    assert all(c.license and c.attribution for c in CORPORA)
    assert {c.name for c in CORPORA if c.share_alike} == {"WikiMatrix"}
    assert not any(c.enabled for c in CORPORA if c.share_alike)  # off unless asked for


def test_resolve_url_uses_the_opus_api():
    seen = []

    def fetch_json(url):
        seen.append(url)
        return {"corpora": [{"url": "https://object.pouta.csc.fi/OPUS-ALT/v2019/moses/en-vi.txt.zip"}]}

    alt = next(c for c in CORPORA if c.name == "ALT")
    assert resolve_url(alt, fetch_json).endswith("/moses/en-vi.txt.zip")
    assert "corpus=ALT" in seen[0] and "preprocessing=moses" in seen[0]


def test_reader_aligns_lines_strips_bom_crlf_and_stops_at_a_mismatch(tmp_path, capsys):  # RF1
    z = fake_zip(tmp_path / "a.zip", ["﻿Hello.\r", "Bye."], ["Xin chào.\r", "Tạm biệt."])
    assert list(read_moses_zip(z)) == [("Hello.", "Xin chào."), ("Bye.", "Tạm biệt.")]
    bad = fake_zip(tmp_path / "b.zip", ["One.", "Two.", "Three."], ["Một.", "Hai."])
    assert list(read_moses_zip(bad)) == [("One.", "Một."), ("Two.", "Hai.")]
    assert "mismatch" in capsys.readouterr().out


def test_build_writes_train_dev_licenses_and_keeps_heldout_out(tmp_path):  # RF3
    zips = {
        "ALT": fake_zip(tmp_path / "alt.zip", [f"Line number {i}." for i in range(300)], [f"Dòng số {i}." for i in range(300)]),
        "Tatoeba": fake_zip(tmp_path / "tat.zip", ["Hi.", "Go now.", "https://x.com"], ["Chào.", "Đi ngay.", "https://x.com"]),
    }
    chosen = [c for c in CORPORA if c.name in zips]

    def download(corpus, dest):
        dest.write_bytes(zips[corpus.name].read_bytes())
        return dest

    stats = build(tmp_path / "out", chosen, download=download, heldout={"Go now."}, seed=1)
    train = (tmp_path / "out" / "train.tsv").read_text(encoding="utf-8").splitlines()
    dev = (tmp_path / "out" / "dev.tsv").read_text(encoding="utf-8").splitlines()
    assert len(train) + len(dev) == 301 and len(dev) == 3  # 1 %, the URL pair and the held-out line dropped
    assert not any(l.startswith("Go now.\t") for l in train + dev)
    lic = (tmp_path / "out" / "DATA_LICENSES.md").read_text(encoding="utf-8")
    assert "ALT" in lic and "CC BY 4.0" in lic and "Tatoeba" in lic
    assert json.loads((tmp_path / "out" / "stats.json").read_text(encoding="utf-8"))["ALT"]["kept"] == 300
    assert stats["total"] == 301
