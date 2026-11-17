from pathlib import Path

import pytest

from app.config import ConfigError, load_config


def test_defaults_match_spec():
    c = load_config(None)
    assert c.translator.model == "vinai-en2vi" and c.translator.beam_size == 2 and c.translator.intra_threads == 2
    assert c.ocr.engine == "windows"
    assert (c.live.interval_ms, c.live.settle_ms, c.live.area_min_interval_ms) == (300, 250, 1000)
    assert c.hotkeys.translate_fullscreen == "ctrl+alt+f"


def test_yaml_overrides_one_key(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("translator:\n  beam_size: 1\n", encoding="utf-8")
    c = load_config(p)
    assert c.translator.beam_size == 1 and c.translator.model == "vinai-en2vi"


def test_unknown_key_is_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("translator:\n  beam_sise: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="beam_sise"):
        load_config(p)


def test_unknown_section_is_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("translater:\n  model: x\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="translater"):
        load_config(p)


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "nope.yaml").translator.model == "vinai-en2vi"


def test_repo_config_yaml_loads():
    assert load_config(Path(__file__).parents[1] / "config.yaml").translator.model == "vinai-en2vi"


def test_null_means_default(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("paths:\n  data_dir: null\n", encoding="utf-8")
    assert load_config(p).paths.data_dir.endswith("ScreenTrans")
