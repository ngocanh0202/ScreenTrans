"""Settings → Quản lý model (Windows)."""
from app.gui.models_dialog import ModelsDialog
from app.models import ModelDownloadError

MANIFEST = [
    {"id": "opus-mt-en-vi", "version": "1", "label": "opus-mt (nhanh)", "files": [{"size": 78_000_000}]},
    {"id": "screentrans-en-vi", "version": "2", "label": "ScreenTrans", "files": [{"size": 80_000_000}]},
]


def _installed(tmp_path, model_id, version):
    d = tmp_path / "models" / model_id / version
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"w")
    (d / ".complete").write_text(version, encoding="utf-8")


def _dialog(qtbot, tmp_path, used, fetch=lambda url: MANIFEST, download=None, pick=None):
    def fake_download(model_id, url, data_dir, progress=None):
        progress(5, 10)
        _installed(tmp_path, model_id, next(m["version"] for m in MANIFEST if m["id"] == model_id))

    d = ModelsDialog(tmp_path, "https://hf/manifest.json", "opus-mt-en-vi", used.append, fetch=fetch,
                     download=download or fake_download, pick_folder=pick)
    qtbot.addWidget(d)
    return d


def test_rows_show_status_and_the_active_model(qtbot, tmp_path):
    _installed(tmp_path, "opus-mt-en-vi", "1")
    d = _dialog(qtbot, tmp_path, [])
    assert [(r.id, r.status, r.active) for r in d.rows] == [("opus-mt-en-vi", "installed", True),
                                                            ("screentrans-en-vi", "missing", False)]
    assert "đang dùng" in d.table.item(0, 0).text() and d.table.item(1, 3).text() == "80 MB"
    d.table.selectRow(0)
    assert not d.delete_button.isEnabled() and not d.use_button.isEnabled()  # the model in use stays


def test_use_a_missing_model_downloads_it_then_switches(qtbot, tmp_path):
    _installed(tmp_path, "opus-mt-en-vi", "1")
    used = []
    d = _dialog(qtbot, tmp_path, used)
    d.table.selectRow(1)
    d.use_selected()
    qtbot.waitUntil(lambda: used == ["screentrans-en-vi"], timeout=3000)
    assert d.rows[1].status == "installed" and d.rows[1].active


def test_delete_and_offline(qtbot, tmp_path):
    _installed(tmp_path, "opus-mt-en-vi", "1")
    _installed(tmp_path, "screentrans-en-vi", "2")

    def offline(url):
        raise ModelDownloadError("no network")

    d = _dialog(qtbot, tmp_path, [], fetch=offline)
    assert "Không đọc được" in d.note.text() and [r.id for r in d.rows] == ["opus-mt-en-vi", "screentrans-en-vi"]
    d.table.selectRow(1)
    d.delete_selected()
    assert [r.id for r in d.rows] == ["opus-mt-en-vi"]


def test_a_failed_download_is_reported(qtbot, tmp_path):
    def broken(model_id, url, data_dir, progress=None):
        raise ModelDownloadError("SHA-256 mismatch")

    d = _dialog(qtbot, tmp_path, [], download=broken)
    d.table.selectRow(1)
    d.download_selected()
    qtbot.waitUntil(lambda: "SHA-256" in d.note.text(), timeout=3000)
    assert d.get_button.isEnabled()


def test_add_a_model_from_a_folder(qtbot, tmp_path):
    src = tmp_path / "src" / "my fine-tune"
    src.mkdir(parents=True)
    (src / "model.bin").write_bytes(b"w")
    data = tmp_path / "data"
    used = []
    d = ModelsDialog(data, "u", "opus-mt-en-vi", used.append, fetch=lambda url: [], pick_folder=lambda: str(src))
    qtbot.addWidget(d)
    d.import_folder()
    assert [r.id for r in d.rows] == ["my-fine-tune"] and (data / "models" / "my-fine-tune" / "local" / "model.bin").is_file()


def test_the_window_does_not_close_while_downloading(qtbot, tmp_path):
    import threading

    gate = threading.Event()

    def slow(model_id, url, data_dir, progress=None):
        gate.wait(5)
        raise ModelDownloadError("stopped")

    d = _dialog(qtbot, tmp_path, [], download=slow)
    d.show()
    d.table.selectRow(1)
    d.download_selected()
    d.accept()
    assert d.isVisible() and "chờ tải xong" in d.note.text()
    gate.set()
    qtbot.waitUntil(lambda: d._busy is None, timeout=3000)
    d.accept()
    assert not d.isVisible()
