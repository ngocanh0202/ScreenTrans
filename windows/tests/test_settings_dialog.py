from app.gui.settings_dialog import SettingsDialog, SettingsValues

V = SettingsValues(style="match", text_scale=1.0, long_text="grow", model="vinai-en2vi",
                   hotkeys={"Dịch vùng": "Ctrl+Alt+T"}, ocr="windows")


def test_dialog_shows_and_returns_the_values(qtbot):
    d = SettingsDialog(V)
    qtbot.addWidget(d)
    assert d.values() == V
    d.readable.setChecked(True)
    d.scale.setCurrentIndex(d.scale.findData(1.25))
    d.shrink.setChecked(True)
    d.model.setCurrentIndex(d.model.findData("opus-mt-en-vi"))
    d.ocr.setCurrentIndex(d.ocr.findData("rapid"))
    got = d.values()
    assert (got.style, got.text_scale, got.long_text, got.model) == ("classic", 1.25, "shrink", "opus-mt-en-vi")
    assert got.ocr == ("rapid" if d.ocr.model().item(d.ocr.findData("rapid")).isEnabled() else "windows")


def test_only_engines_of_this_platform_are_listed(qtbot):
    d = SettingsDialog(V)
    qtbot.addWidget(d)
    assert [d.ocr.itemData(i) for i in range(d.ocr.count())] == ["windows", "rapid"]


def test_settings_file_round_trip_and_junk(tmp_path):
    from app.gui.settings_dialog import load_settings, save_settings

    assert load_settings(tmp_path) == {}
    save_settings(tmp_path, {"text_scale": 1.5, "long_text": "shrink", "model": "opus-mt-en-vi"})
    assert load_settings(tmp_path) == {"text_scale": 1.5, "long_text": "shrink", "model": "opus-mt-en-vi"}
    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")
    assert load_settings(tmp_path) == {}


def test_an_engine_missing_on_this_machine_is_never_returned(qtbot, monkeypatch):
    """CI / the exe have no RapidOCR: a saved "rapid" or a programmatic pick still gives Windows OCR."""
    from app.ocr import engines

    monkeypatch.setattr(engines, "available", lambda name: name == "windows")
    d = SettingsDialog(SettingsValues(**{**V.__dict__, "ocr": "rapid"}))
    qtbot.addWidget(d)
    assert d.values().ocr == "windows"
    d.ocr.setCurrentIndex(d.ocr.findData("rapid"))
    assert d.values().ocr == "windows"
