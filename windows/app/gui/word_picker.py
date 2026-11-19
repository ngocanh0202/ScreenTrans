"""A sentence as selectable words: click one word, shift-click or drag to select a run (glossary terms)."""
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.text.terms import span, tokens

GAP_X, GAP_Y, PAD_X, PAD_Y = 4, 4, 5, 2


class WordPicker(QWidget):
    selectionChanged = Signal(str)

    def __init__(self, sentence: str, parent=None):
        super().__init__(parent)
        self.tokens = tokens(sentence)
        self._sel: tuple[int, int] | None = None
        self._anchor: int | None = None
        self._dragging = False
        self._rects: list[QRect] = []
        self._laid_for = -1
        self.setCursor(Qt.PointingHandCursor)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    # ---- selection ----------------------------------------------------------------------------------------
    def selection(self) -> str:
        if self._sel is None:
            return ""
        a, b = self._sel
        return span(self.tokens, min(a, b), max(a, b))

    def clear_selection(self) -> None:
        if self._sel is not None:
            self._sel = self._anchor = None
            self.update()
            self.selectionChanged.emit("")

    def _select(self, a: int, b: int) -> None:
        self._sel = (a, b)
        self.update()
        self.selectionChanged.emit(self.selection())

    # ---- layout -------------------------------------------------------------------------------------------
    def _layout(self, width: int) -> list[QRect]:
        fm = QFontMetrics(self.font())
        rects, x, y = [], 0, 0
        h = fm.height() + 2 * PAD_Y
        for tok in self.tokens:
            w = fm.horizontalAdvance(tok) + 2 * PAD_X
            if x > 0 and x + w > width:
                x, y = 0, y + h + GAP_Y
            rects.append(QRect(x, y, w, h))
            x += w + GAP_X
        return rects

    def _ensure_layout(self) -> None:
        if self._laid_for != self.width():
            self._rects = self._layout(max(self.width(), 50))
            self._laid_for = self.width()

    def word_rect(self, i: int) -> QRect:
        self._ensure_layout()
        return QRect(self._rects[i])

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        rects = self._layout(max(width, 50))
        return (rects[-1].bottom() + 1) if rects else 0

    def sizeHint(self) -> QSize:
        return QSize(400, self.heightForWidth(400))

    def resizeEvent(self, event):
        self._laid_for = -1
        super().resizeEvent(event)

    def _index_at(self, pos) -> int | None:
        self._ensure_layout()
        for i, r in enumerate(self._rects):
            if r.contains(pos):
                return i
        return None

    # ---- input / painting ---------------------------------------------------------------------------------
    def mousePressEvent(self, event):
        i = self._index_at(event.position().toPoint())
        if i is None:
            return
        if event.modifiers() & Qt.ShiftModifier and self._anchor is not None:
            self._select(self._anchor, i)
        else:
            self._anchor = i
            self._select(i, i)
        self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging and self._anchor is not None:
            i = self._index_at(event.position().toPoint())
            if i is not None and self._sel != (self._anchor, i):
                self._select(self._anchor, i)

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def paintEvent(self, event):
        self._ensure_layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lo, hi = (min(self._sel), max(self._sel)) if self._sel else (-1, -2)
        for i, (tok, r) in enumerate(zip(self.tokens, self._rects)):
            chosen = lo <= i <= hi
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(37, 99, 235) if chosen else QColor(0, 0, 0, 18))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor(255, 255, 255) if chosen else self.palette().text().color())
            p.drawText(r, Qt.AlignCenter, tok)
