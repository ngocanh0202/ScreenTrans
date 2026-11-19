"""compare_engines.py --engine ... --dry-run prints the prompts it would send (no network, no key)."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_engines.py"


def load():
    spec = importlib.util.spec_from_file_location("compare_engines", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dry_run_prints_the_prompts_for_remote_engines(tmp_path, monkeypatch, capsys):
    lines = tmp_path / "x.txt"
    lines.write_text("Hello there.\nWhere are you going?\n", encoding="utf-8")
    mod = load()
    monkeypatch.setattr(mod, "logged_sentences", lambda: [])
    monkeypatch.setattr(sys, "argv", ["compare_engines.py", "--engine", "claude", "--no-samples", "--sentences",
                                      str(lines), "--dry-run", "--data-dir", str(tmp_path)])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "claude" in out and "claude-opus-5-5" in out
    assert "Bạn dịch lời thoại" in out and '["Where are you going?"]' in out and "- Hello there." in out
