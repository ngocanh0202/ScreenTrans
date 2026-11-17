import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from app import cli
from app.cache import TranslationCache
from app.glossary import Glossary
from app.ocr.base import Line
from app.pipeline import Pipeline
from fakes import FakeOcr, FakeTranslator

TESTS = Path(__file__).parent
REPO = TESTS.parents[1]


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "x.png"
    Image.new("RGB", (40, 20)).save(p)
    return p


@pytest.fixture
def fake(monkeypatch):
    def install(lines, fn=lambda s: "VI " + s):
        monkeypatch.setattr(cli, "build_pipeline", lambda config, args: Pipeline(
            FakeOcr(lines), FakeTranslator(fn), Glossary([]), TranslationCache(10, None)))
    return install


DIALOGUE = [Line("Druvis Ill", 37, 13, 149, 29), Line("A dream far too vivid.", 26, 78, 500, 31)]


def test_prints_name_and_translation(fake, image, capsys):
    fake(DIALOGUE)
    assert cli.main(["--image", str(image)]) == 0
    out = capsys.readouterr().out
    assert "[Druvis III]" in out and "VI A dream far too vivid." in out


def test_show_source(fake, image, capsys):
    fake(DIALOGUE)
    cli.main(["--image", str(image), "--show-source"])
    assert "EN: A dream far too vivid." in capsys.readouterr().out


def test_json_output(fake, image, capsys):
    fake(DIALOGUE)
    cli.main(["--image", str(image), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert [s["kind"] for s in data["segments"]] == ["name", "text"]
    assert data["segments"][1]["translation"] == "VI A dream far too vivid."


def test_timings_go_to_stderr(fake, image, capsys):
    fake(DIALOGUE)
    cli.main(["--image", str(image), "--timings"])
    captured = capsys.readouterr()
    assert "total" in captured.err and "total" not in captured.out


def test_no_text(fake, image, capsys):
    fake([])
    assert cli.main(["--image", str(image)]) == 0
    assert "(không tìm thấy chữ)" in capsys.readouterr().out


def test_missing_model_dir_exit_2(image, tmp_path, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"paths:\n  data_dir: '{tmp_path.as_posix()}'\n", encoding="utf-8")
    assert cli.main(["--image", str(image), "--config", str(cfg), "--model-dir", str(tmp_path / "nope")]) == 2
    assert "models.export" in capsys.readouterr().err


def test_bad_arguments_exit_4(capsys):
    assert cli.main([]) == 4
    assert cli.main(["--screen", "1,2,3"]) == 4


def test_console_without_utf8_still_prints_vietnamese(image):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    proc = subprocess.run(
        [sys.executable, str(TESTS / "cli_fake_runner.py"), "--image", str(image)],
        capture_output=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "Xin chào, Việt Nam!" in proc.stdout.decode("utf-8")


@pytest.mark.local
def test_end_to_end_real_model(capsys):
    img = REPO / "spikes" / "ocr" / "data" / "rv_02_short.png"
    model = REPO / "models" / "out" / "vinai-en2vi-ct2"
    if not img.is_file() or not (model / "screentrans_model.json").is_file():
        pytest.skip("sample image or model missing")
    assert cli.main(["--image", str(img), "--model-dir", str(model)]) == 0
    out = capsys.readouterr().out
    assert "[Druvis III]" in out
    assert any(c in out for c in "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")


def _cfg(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"paths:\n  data_dir: '{tmp_path.as_posix()}'\n", encoding="utf-8")
    return cfg


def test_without_model_dir_downloads_from_manifest(image, tmp_path, monkeypatch, capsys):
    calls = []

    def fake_ensure(model_id, manifest_url, data_dir, platform="windows", progress=None):
        calls.append((model_id, Path(data_dir)))
        return tmp_path / "empty-model"

    monkeypatch.setattr(cli, "ensure_model", fake_ensure)
    assert cli.main(["--image", str(image), "--config", str(_cfg(tmp_path))]) == 2  # empty dir -> ModelNotFound
    assert calls == [("vinai-en2vi", tmp_path)]


def test_download_error_exit_2(image, tmp_path, monkeypatch, capsys):
    from app.models import ModelDownloadError

    def fail(*a, **k):
        raise ModelDownloadError("network down, pass --model-dir")

    monkeypatch.setattr(cli, "ensure_model", fail)
    assert cli.main(["--image", str(image), "--config", str(_cfg(tmp_path))]) == 2
    assert "--model-dir" in capsys.readouterr().err
