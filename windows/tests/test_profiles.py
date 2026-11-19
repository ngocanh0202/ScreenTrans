import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.live.mask import ignore_mask
from app.live.thumb import diff, gray_thumb
from app.profiles import Profile, ProfileStore, to_px, to_rel

FIXTURES = sorted((Path(__file__).parents[2] / "shared" / "fixtures" / "profiles").glob("*.json"))


def test_fixture_set_present():
    assert len(FIXTURES) >= 5


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    inp = data["input"]
    p = Profile.parse(inp if isinstance(inp, str) else json.dumps(inp))
    assert (p.to_json() if p else None) == data["expected"]


def test_round_trip():
    p = Profile("a.exe", "A", scope="screen", regions=[(0.1, 0.2, 0.3, 0.4)], overrides={"Hi.": "Chào."})
    assert Profile.parse(json.dumps(p.to_json())) == p


def test_store_saves_reads_and_quarantines_broken_files(tmp_path):
    store = ProfileStore(tmp_path)
    assert store.get("a.exe") is None
    p = store.get_or_default("a.exe", "Game A")
    assert p.name == "Game A" and store.get("a.exe") is None  # default is not saved by itself
    store.save(p)
    assert store.get("a.exe") == p
    (tmp_path / "b.exe.json").write_text("{broken", encoding="utf-8")
    assert store.get("b.exe") is None and (tmp_path / "b.exe.json.bad").exists()


def test_migrate_phase4a_keeps_the_old_region(tmp_path):
    (tmp_path / "live_regions.json").write_text("[[192, 540, 1536, 270]]", encoding="utf-8")
    (tmp_path / "live_mode.txt").write_text("area", encoding="utf-8")
    store = ProfileStore(tmp_path / "profiles")
    store.migrate_phase4a(tmp_path, screen=(0, 0, 1920, 1080))
    p = store.get("_default")
    assert p.scope == "region" and p.regions == [(0.1, 0.5, 0.8, 0.25)]
    assert not (tmp_path / "live_regions.json").exists()
    store.migrate_phase4a(tmp_path, screen=(0, 0, 1920, 1080))  # nothing left to migrate: no change
    assert store.get("_default") == p


def test_relative_coordinates_follow_the_window():
    window = (100, 50, 1280, 720)
    assert to_px((0.5, 0.5, 0.25, 0.25), window) == (740, 410, 320, 180)
    assert to_rel((740, 410, 320, 180), window) == (0.5, 0.5, 0.25, 0.25)


def test_ignore_mask_hides_part_of_the_region_from_the_diff():
    a = Image.new("RGB", (640, 160), (0, 0, 0))
    b = a.copy()
    b.paste((255, 255, 255), (0, 0, 320, 160))  # left half changes
    ta, tb = gray_thumb(a), gray_thumb(b)
    left = ignore_mask((0, 0, 640, 160), [(0, 0, 320, 160)], ta.shape[1], ta.shape[0])
    assert diff(ta, tb, left) == pytest.approx(0.0)
    right = ignore_mask((0, 0, 640, 160), [(320, 0, 320, 160)], ta.shape[1], ta.shape[0])
    assert diff(ta, tb, right) == ta.size / 2  # every cell of the left half
    everything = ignore_mask((0, 0, 640, 160), [(0, 0, 640, 160)], ta.shape[1], ta.shape[0])
    assert not everything.any() and diff(ta, tb, everything) == 0.0
    assert isinstance(diff(ta, tb), float) and diff(ta, tb) == ta.size / 2
    assert np.array_equal(ignore_mask((0, 0, 640, 160), [], 64, 16), np.ones((16, 64), bool))


def test_m1_a_profile_that_is_not_utf8_is_quarantined_not_a_crash(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path)
    (tmp_path / "a.exe.json").write_bytes(b'{"id": "a.exe", "name": "\xe1\xbb"}\xff')
    assert store.get("a.exe") is None and (tmp_path / "a.exe.json.bad").exists()
    (tmp_path / "b.exe.json").write_text("{broken", encoding="utf-8")
    import os

    def fail(*a, **k):
        raise OSError("locked")

    monkeypatch.setattr(os, "replace", fail)
    assert store.get("b.exe") is None  # cannot even rename it: still no crash
