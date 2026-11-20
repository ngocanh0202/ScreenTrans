"""Cài đặt → Quản lý model: the published models (Hugging Face manifest) and the ones on this PC; download / update
(with progress), delete, use, or add an exported model from a folder. Rows: app/model_catalog.py."""
import re
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from app import models as store
from app.gui.overlay import FONT
from app.model_catalog import ModelRow, catalog

STATUS = {"installed": "Đã tải", "missing": "Chưa tải", "update": "Có bản mới", "bundled": "Có sẵn"}


class _Bridge(QObject):
    progress = Signal(int, int)
    finished = Signal(str, str)  # model id, error ("" = ok)


def _mb(n: int) -> str:
    return f"{n / 1e6:.0f} MB" if n else ""


class ModelsDialog(QDialog):
    def __init__(self, data_dir: Path, manifest_url: str, active: str, on_use: Callable[[str], None], parent=None,
                 fetch=store.fetch_manifest, download=store.ensure_model, pick_folder=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Quản lý model — ScreenTrans")
        self.setFont(QFont(FONT, 10))
        self.resize(640, 380)
        self.data_dir, self.manifest_url, self.active, self.on_use = Path(data_dir), manifest_url, active, on_use
        self._fetch, self._download = fetch, download
        self._pick_folder = pick_folder or (lambda: QFileDialog.getExistingDirectory(self, "Thư mục model (CTranslate2)"))
        self.rows: list[ModelRow] = []
        self._busy: str | None = None
        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_progress)
        self._bridge.finished.connect(self._on_finished)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Model", "Trạng thái", "Phiên bản", "Cần tải"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.get_button = QPushButton("Tải về")
        self.get_button.clicked.connect(self.download_selected)
        self.use_button = QPushButton("Dùng model này")
        self.use_button.clicked.connect(self.use_selected)
        self.delete_button = QPushButton("Xóa")
        self.delete_button.clicked.connect(self.delete_selected)
        self.import_button = QPushButton("Thêm từ thư mục…")
        self.import_button.clicked.connect(self.import_folder)
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        tools = QHBoxLayout()
        for b in (self.get_button, self.use_button, self.delete_button, self.import_button):
            tools.addWidget(b)
        tools.addStretch(1)
        tools.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addLayout(tools)
        self.refresh()

    def done(self, result: int) -> None:
        if self._busy is not None:  # the download thread still reports here: close once it is over
            self.note.setText("Đang tải model, chờ tải xong rồi đóng.")
            return
        super().done(result)

    def closeEvent(self, event) -> None:
        if self._busy is not None:
            self.note.setText("Đang tải model, chờ tải xong rồi đóng.")
            event.ignore()
            return
        super().closeEvent(event)

    # ---- data ------------------------------------------------------------------------------------
    def refresh(self) -> None:
        try:
            manifest = self._fetch(self.manifest_url)
            self.note.setText("Model đã tải nằm trong thư mục dữ liệu của app. Model mới hơn được tải khi bấm "
                              "\"Cập nhật\" (hoặc tự động khi mở app với model đang dùng).")
        except store.ModelDownloadError:
            manifest = []
            self.note.setText("Không đọc được danh sách model trên mạng: chỉ hiện model đã có trên máy.")
        self.rows = catalog(manifest, store.installed(self.data_dir), {}, self.active)
        selected = self.selected().id if self.selected() else self.active
        self.table.setRowCount(0)
        for r in self.rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            name = r.label + ("  ✓ đang dùng" if r.active else "")
            for col, text in enumerate([name, STATUS[r.status], r.version or "", _mb(r.download)]):
                self.table.setItem(i, col, QTableWidgetItem(text))
            if r.id == selected:
                self.table.selectRow(i)
        self._update_buttons()

    def selected(self) -> ModelRow | None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        return self.rows[min(rows)] if rows and min(rows) < len(self.rows) else None

    def _update_buttons(self) -> None:
        r = self.selected()
        idle = self._busy is None
        self.get_button.setText("Cập nhật" if r and r.status == "update" else "Tải về")
        self.get_button.setEnabled(idle and r is not None and r.status in ("missing", "update"))
        self.use_button.setEnabled(idle and r is not None and not r.active)
        self.delete_button.setEnabled(idle and r is not None and r.deletable and not r.active)
        self.import_button.setEnabled(idle)

    # ---- actions ---------------------------------------------------------------------------------
    def download_selected(self, then_use: bool = False) -> None:
        r = self.selected()
        if r is None or self._busy is not None:
            return
        self._busy = r.id
        self._then_use = then_use
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.note.setText(f"Đang tải {r.label}…")
        self._update_buttons()

        def run(model_id: str) -> None:
            try:
                self._download(model_id, self.manifest_url, self.data_dir,
                               progress=lambda done, total: self._bridge.progress.emit(done, total))
                self._bridge.finished.emit(model_id, "")
            except Exception as e:  # shown to the user; the dialog stays usable
                self._bridge.finished.emit(model_id, str(e))

        threading.Thread(target=run, args=(r.id,), daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_finished(self, model_id: str, error: str) -> None:
        self._busy = None
        self.progress.setVisible(False)
        self.refresh()
        if error:
            self.note.setText(f"Không tải được: {error}")
        elif getattr(self, "_then_use", False):
            self._use(model_id)

    def use_selected(self) -> None:
        r = self.selected()
        if r is None:
            return
        if r.status == "missing":  # download first, then switch
            self.download_selected(then_use=True)
            return
        self._use(r.id)

    def _use(self, model_id: str) -> None:
        self.active = model_id
        self.on_use(model_id)
        self.refresh()

    def delete_selected(self) -> None:
        r = self.selected()
        if r is None or r.active or not r.deletable:
            return
        store.delete_model(self.data_dir, r.id)
        self.refresh()

    def import_folder(self) -> None:
        folder = self._pick_folder()
        if not folder:
            return
        model_id = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(folder).name).strip("-.") or "my-model"
        try:
            store.import_folder(Path(folder), self.data_dir, model_id)
        except store.ModelDownloadError as e:
            self.note.setText(str(e))
            return
        self.refresh()
        self.note.setText(f"Đã thêm \"{model_id}\". Chọn nó rồi bấm \"Dùng model này\".")
