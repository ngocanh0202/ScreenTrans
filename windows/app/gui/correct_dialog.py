"""Correct a translation (AGENT.md §9): fixed sentences become profile overrides, terms go to the game glossary.

Terms are picked, not typed: select words of a source sentence (click, shift-click or drag), then
"Giữ nguyên" or "Dịch cố định" (only the Vietnamese is typed). Likely names are suggested.
"""
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.gui.overlay import FONT
from app.gui.word_picker import WordPicker
from app.pipeline import Segment

ROLE = Qt.UserRole


@dataclass
class Correction:
    source: str
    machine: str
    corrected: str


def parse_terms(text: str) -> list[tuple[str, str | None]]:
    """One term per line, `source = target`; an empty target means keep the source unchanged."""
    out = []
    for line in text.splitlines():
        if "=" not in line:
            continue
        source, target = (part.strip() for part in line.split("=", 1))
        if source:
            out.append((source, target or None))
    return out


def _chips() -> QListWidget:
    w = QListWidget()
    w.setFlow(QListWidget.LeftToRight)
    w.setWrapping(True)
    w.setResizeMode(QListWidget.Adjust)
    w.setSpacing(3)
    w.setFixedHeight(56)
    return w


class CorrectDialog(QDialog):
    def __init__(self, segments: list[Segment], parent=None, common: set[str] | None = None,
                 known: set[str] = frozenset()):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Sửa bản dịch — ScreenTrans")
        self.setFont(QFont(FONT, 10))
        self._segments = [s for s in segments if s.kind == "text" and s.translation]
        self._terms: list[tuple[str, str | None]] = []
        self._picked: WordPicker | None = None

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        self.edits: list[QLineEdit] = []
        self.pickers: list[WordPicker] = []
        for row, seg in enumerate(self._segments):
            picker = WordPicker(seg.source)
            picker.selectionChanged.connect(lambda text, pk=picker: self._on_pick(pk, text))
            edit = QLineEdit(seg.translation)
            grid.addWidget(picker, row * 2, 0)
            grid.addWidget(edit, row * 2 + 1, 0)
            self.pickers.append(picker)
            self.edits.append(edit)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)

        # selected words -> keep / fixed translation
        self.selected_label = QLabel("Chọn chữ ở câu gốc (bấm, Shift+bấm hoặc kéo) để thêm thuật ngữ.")
        self.selected_label.setStyleSheet("color: #666;")
        self.keep_button = QPushButton("Giữ nguyên")
        self.target = QLineEdit()
        self.target.setPlaceholderText("Bản dịch cố định")
        self.fixed_button = QPushButton("Dịch cố định")
        self.keep_button.clicked.connect(lambda: self._add_picked(None))
        self.fixed_button.clicked.connect(lambda: self._add_picked(self.target.text().strip() or ""))
        self.target.installEventFilter(self)  # Enter adds the term; it must not press "Save" and close the window
        bar = QHBoxLayout()
        bar.addWidget(self.keep_button)
        bar.addWidget(self.target, 1)
        bar.addWidget(self.fixed_button)
        self._enable_bar(False)

        self.term_list = _chips()  # added terms; click one to remove it
        self.term_list.itemClicked.connect(self.remove_term)
        self.suggestions = _chips()  # likely names; click one to keep it as is
        self.suggestions.itemClicked.connect(self.add_suggestion)
        if common is None:
            from app.glossary import load_common_words

            common = load_common_words()
        from app.text.terms import suggest_names

        for name in suggest_names([s.source for s in self._segments], common, set(known)):
            item = QListWidgetItem(f"{name}  +")
            item.setData(ROLE, name)
            self.suggestions.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Sửa bản dịch (lần sau gặp đúng câu này sẽ dùng bản của bạn):"))
        layout.addWidget(scroll, 1)
        layout.addWidget(self.selected_label)
        layout.addLayout(bar)
        layout.addWidget(QLabel("Thuật ngữ đã thêm (bấm để xóa):"))
        layout.addWidget(self.term_list)
        if self.suggestions.count():
            layout.addWidget(QLabel("Gợi ý tên riêng (bấm để giữ nguyên):"))
            layout.addWidget(self.suggestions)
        layout.addWidget(buttons)
        self.resize(680, min(640, 300 + 70 * len(self._segments)))

    def eventFilter(self, obj, event):
        if obj is self.target and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.fixed_button.click()
            return True
        return super().eventFilter(obj, event)

    # ---- picking ------------------------------------------------------------------------------------------
    def _enable_bar(self, on: bool) -> None:
        for w in (self.keep_button, self.target, self.fixed_button):
            w.setEnabled(on)

    def _on_pick(self, picker: WordPicker, text: str) -> None:
        if text and self._picked is not None and self._picked is not picker:
            self._picked.clear_selection()  # one selection at a time, across sentences
        self._picked = picker if text else (None if self._picked is picker else self._picked)
        self.selected_label.setText(f"Đã chọn: “{text}”" if text else
                                    "Chọn chữ ở câu gốc (bấm, Shift+bấm hoặc kéo) để thêm thuật ngữ.")
        self._enable_bar(bool(text))

    def _add_picked(self, target: str | None) -> None:
        if self._picked is None or target == "":  # "Dịch cố định" needs the Vietnamese
            return
        source = self._picked.selection()
        if source:
            self._add_term(source, target)
        self.target.clear()
        self._picked.clear_selection()

    def _add_term(self, source: str, target: str | None) -> None:
        self._terms = [t for t in self._terms if t[0].lower() != source.lower()] + [(source, target)]
        self.term_list.clear()
        for src, dst in self._terms:
            item = QListWidgetItem(f"{src} (giữ nguyên)  ✕" if dst is None else f"{src} → {dst}  ✕")
            item.setData(ROLE, src)
            self.term_list.addItem(item)

    def remove_term(self, item: QListWidgetItem) -> None:
        src = item.data(ROLE)
        self._terms = [t for t in self._terms if t[0] != src]
        self.term_list.takeItem(self.term_list.row(item))

    def add_suggestion(self, item: QListWidgetItem) -> None:
        self._add_term(item.data(ROLE), None)
        self.suggestions.takeItem(self.suggestions.row(item))

    # ---- results ------------------------------------------------------------------------------------------
    def corrections(self) -> list[Correction]:
        out = []
        for seg, edit in zip(self._segments, self.edits):
            text = edit.text().strip()
            if text and text != seg.translation:
                out.append(Correction(seg.source, seg.translation, text))
        return out

    def parsed_terms(self) -> list[tuple[str, str | None]]:
        return list(self._terms)
