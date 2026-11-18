"""Correct a translation (AGENT.md §9): fixed sentences become profile overrides, terms go to the game glossary."""
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QScrollArea, QVBoxLayout, QWidget)

from app.gui.overlay import FONT
from app.pipeline import Segment


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


class CorrectDialog(QDialog):
    def __init__(self, segments: list[Segment], parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Sửa bản dịch — ScreenTrans")
        self.setFont(QFont(FONT, 10))
        self._segments = [s for s in segments if s.kind == "text" and s.translation]
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        self.edits: list[QLineEdit] = []
        for row, seg in enumerate(self._segments):
            src = QLabel(seg.source)
            src.setWordWrap(True)
            src.setStyleSheet("color: #666;")
            src.setTextInteractionFlags(Qt.TextSelectableByMouse)
            edit = QLineEdit(seg.translation)
            grid.addWidget(src, row * 2, 0)
            grid.addWidget(edit, row * 2 + 1, 0)
            self.edits.append(edit)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        self.terms = QPlainTextEdit()
        self.terms.setPlaceholderText("Thuật ngữ, mỗi dòng một mục:\nArcanist =            (giữ nguyên)\nStorm = Bão Tố        (dịch cố định)")
        self.terms.setFixedHeight(90)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Sửa bản dịch (lần sau gặp đúng câu này sẽ dùng bản của bạn):"))
        layout.addWidget(scroll, 1)
        layout.addWidget(self.terms)
        layout.addWidget(buttons)
        self.resize(640, min(520, 160 + 60 * len(self._segments)))

    def corrections(self) -> list[Correction]:
        out = []
        for seg, edit in zip(self._segments, self.edits):
            text = edit.text().strip()
            if text and text != seg.translation:
                out.append(Correction(seg.source, seg.translation, text))
        return out

    def parsed_terms(self) -> list[tuple[str, str | None]]:
        return parse_terms(self.terms.toPlainText())
