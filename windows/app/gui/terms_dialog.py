"""Cài đặt → Thuật ngữ: view / add / edit / delete the game's own glossary terms (rules: app/text/term_edit.py)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from app.gui.overlay import FONT
from app.text.term_edit import Row, clean

CS_ROLE = Qt.UserRole + 1  # the row's case_sensitive flag, kept as loaded


class TermsDialog(QDialog):
    def __init__(self, rows: list[Row], game: str = "", parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"Thuật ngữ{f' — {game}' if game else ''}")
        self.setFont(QFont(FONT, 10))
        self.resize(560, 420)
        note = QLabel("Từ gốc tiếng Anh và cách dịch. Để trống cột \"Dịch thành\" = giữ nguyên (tên riêng). "
                      "Áp dụng ngay sau khi lưu.")
        note.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Từ gốc", "Dịch thành (trống = giữ nguyên)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for source, target, cs in rows:
            self._append(source, target or "", cs)
        add = QPushButton("Thêm")
        add.clicked.connect(self.add_row)
        remove = QPushButton("Xóa dòng đã chọn")
        remove.clicked.connect(self.remove_selected)
        tools = QHBoxLayout()
        tools.addWidget(add)
        tools.addWidget(remove)
        tools.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(self.table, 1)
        layout.addLayout(tools)
        layout.addWidget(buttons)

    def _append(self, source: str, target: str, cs: bool = True) -> int:
        r = self.table.rowCount()
        self.table.insertRow(r)
        src = QTableWidgetItem(source)
        src.setData(CS_ROLE, cs)
        self.table.setItem(r, 0, src)
        self.table.setItem(r, 1, QTableWidgetItem(target))
        return r

    def add_row(self) -> None:
        r = self._append("", "")
        self.table.setCurrentCell(r, 0)
        self.table.editItem(self.table.item(r, 0))

    def remove_selected(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def rows(self) -> list[Row]:
        """What to save: cleaned (trimmed, no empty sources, duplicates merged)."""
        out: list[Row] = []
        for r in range(self.table.rowCount()):
            src, tgt = self.table.item(r, 0), self.table.item(r, 1)
            cs = src.data(CS_ROLE) if src is not None else True
            out.append((src.text() if src else "", tgt.text() if tgt else "", cs if isinstance(cs, bool) else True))
        return clean(out)
