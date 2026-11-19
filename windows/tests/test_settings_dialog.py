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


def test_translation_engines_key_model_and_privacy_warning(qtbot):
    d = SettingsDialog(SettingsValues(**{**V.__dict__, "saved_keys": ("gemini",), "used_today": 1234}), game="game.exe")
    qtbot.addWidget(d)
    assert [d.engine.itemData(i) for i in range(d.engine.count())] == ["local", "gemini", "openai", "claude", "kaggle"]
    assert d.engine.currentData() == "local" and not d.key.isEnabled() and d.privacy.isHidden()
    assert "1234" in d.usage_label.text()
    d.engine.setCurrentIndex(d.engine.findData("gemini"))
    assert d.key.isEnabled() and not d.privacy.isHidden() and "Gemini" in d.privacy.text()
    assert d.key.text() == "" and "đã lưu" in d.key.placeholderText()  # a saved key is never shown
    assert d.values().keys == {}  # untouched: nothing to save
    d.engine.setCurrentIndex(d.engine.findData("claude"))
    assert d.llm_model.text() == "claude-opus-5-5"
    d.key.setText("  sk-ant-1\n")
    d.llm_model.setText("claude-haiku-5-5")
    d.limit.setValue(1000)
    v = d.values()
    assert (v.engine, v.keys, v.llm_models["claude"], v.daily_limit) == ("claude", {"claude": "sk-ant-1"},
                                                                         "claude-haiku-5-5", 1000)
    d.engine.setCurrentIndex(d.engine.findData("kaggle"))
    assert d.kaggle_url.isEnabled()


def test_game_notes_delete_key_and_default_models_not_saved(qtbot):
    d = SettingsDialog(SettingsValues(**{**V.__dict__, "engine": "gemini", "saved_keys": ("gemini",),
                                         "llm_notes": "Vertin: nữ."}), game="game.exe")
    qtbot.addWidget(d)
    assert d.notes.toPlainText() == "Vertin: nữ."
    assert d.values().llm_models == {}  # the default model name shown is not a choice
    d.llm_model.setText("gemini-2.5-pro")
    assert d.values().llm_models == {"gemini": "gemini-2.5-pro"}
    assert d.delete_key.isEnabled()
    d.delete_key.click()
    v = d.values()
    assert v.delete_keys == ("gemini",) and "gemini" not in v.keys and not d.delete_key.isEnabled()
    d.notes.setPlainText("  Bối cảnh mới.  ")
    assert d.values().llm_notes == "Bối cảnh mới."
    d.engine.setCurrentIndex(d.engine.findData("claude"))  # no saved key for Claude
    assert not d.delete_key.isEnabled()
