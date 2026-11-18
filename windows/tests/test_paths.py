import sys

from app import paths


def test_shared_dir_in_repo():
    assert (paths.shared_dir() / "glossary" / "common.json").is_file()
    assert paths.default_config_path().is_file()


def test_frozen_bundle_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_root() == tmp_path
    assert paths.shared_dir() == tmp_path / "shared"
    assert paths.default_config_path() == tmp_path / "windows" / "config.yaml"
