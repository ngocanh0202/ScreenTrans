"""windows/scripts/bench_models.py with a fake translator (the real run needs exported models)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "windows" / "scripts"))

from bench_models import bench, write_html  # noqa: E402


class Fake:
    def __init__(self, model_dir, beam_size=2, intra_threads=2):
        self.beam = beam_size

    def translate(self, texts):
        return [f"b{self.beam}:{t}" for t in texts]


def test_bench_measures_every_setting_and_keeps_one_output_per_beam(tmp_path):
    r = bench(tmp_path, ["Hi.", "Go."], beams=(1, 2), threads=(1, 2), make=Fake)
    assert [(s["beam"], s["threads"]) for s in r["speed"]] == [(1, 1), (2, 1), (1, 2), (2, 2)]
    assert r["outputs"] == {1: ["b1:Hi.", "b1:Go."], 2: ["b2:Hi.", "b2:Go."]}
    out = tmp_path / "b.html"
    write_html(out, ["Hi.", "Go."], {"opus": r})
    assert "b2:Go." in out.read_text(encoding="utf-8")
