"""Private distillation data with the user's own key (fake client, no network)."""
import json

import pytest

from training import distill_data

KEY = "AIza-SECRET-9"


class FakeClient:
    name, model = "Gemini", "gemini-x"

    def __init__(self):
        self.calls = []

    def complete(self, system, user, timeout_s):
        self.calls.append(user)
        sentences = json.loads(user.rsplit("\n", 1)[1])
        return json.dumps({"translations": [f"VI {s}" for s in sentences]})


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(distill_data, "make_client", lambda engine, key, model="", url="": c)
    monkeypatch.setenv("SCREENTRANS_KEY", KEY)
    return c


def lines(tmp_path, n):
    p = tmp_path / "src.txt"
    p.write_text("\n".join(f"Line {i}." for i in range(n)) + "\n\n", encoding="utf-8")
    return p


def test_estimate_first_then_translate_in_batches(tmp_path, fake, capsys):
    out = tmp_path / "out"
    assert distill_data.main(["--engine", "gemini", "--sentences", str(lines(tmp_path, 45)), "--out", str(out)]) == 1
    assert "--yes" in capsys.readouterr().out and not fake.calls  # an estimate only, nothing sent
    assert distill_data.main(["--engine", "gemini", "--sentences", str(lines(tmp_path, 45)), "--out", str(out),
                              "--yes", "--batch", "20"]) == 0
    rows = (out / "distilled.tsv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 45 and rows[0] == "Line 0.\tVI Line 0." and len(fake.calls) == 3


def test_resume_budget_and_the_key_is_never_written(tmp_path, fake):  # RF4
    out = tmp_path / "out"
    src = lines(tmp_path, 30)
    distill_data.main(["--engine", "gemini", "--sentences", str(src), "--out", str(out), "--yes", "--limit", "10"])
    distill_data.main(["--engine", "gemini", "--sentences", str(src), "--out", str(out), "--yes",
                       "--budget-chars", "60", "--batch", "5"])  # 60 chars ~ 7 short lines: stops after 2 batches
    rows = (out / "distilled.tsv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 20 and len(set(rows)) == 20  # resumed (no duplicates), stopped at the budget
    for f in out.iterdir():
        assert KEY not in f.read_text(encoding="utf-8")


def test_user_corrections_are_added_as_pairs(tmp_path, fake):
    data = tmp_path / "appdata"
    data.mkdir()
    (data / "corrections.jsonl").write_text(json.dumps({"source": "Hi there.", "corrected": "Chào em."}) + "\n",
                                            encoding="utf-8")
    out = tmp_path / "out"
    distill_data.main(["--engine", "gemini", "--sentences", str(lines(tmp_path, 1)), "--out", str(out), "--yes",
                       "--with-corrections", "--data-dir", str(data)])
    rows = (out / "distilled.tsv").read_text(encoding="utf-8").splitlines()
    assert "Hi there.\tChào em." in rows
