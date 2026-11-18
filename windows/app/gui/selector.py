"""Drag-to-select a screen region. Returns physical pixels taken from the real cursor position,
so the region matches mss captures at any DPI scaling and across monitors."""
from typing import Callable

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.gui.win32 import cursor_pos_physical

MIN_SIZE = 8


def normalize_rect(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    return min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)


class _ScreenShade(QWidget):
    def __init__(self, owner: "RegionSelector", geometry: QRect):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._owner = owner
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(geometry)
        self._start: QPoint | None = None
        self._end: QPoint | None = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 77))
        if self._start is not None and self._end is not None:
            r = QRect(self._start, self._end).normalized()
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(r, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(QColor(80, 160, 255), 2))
            p.drawRect(r)

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._owner._finish(None)
            return
        if e.button() == Qt.LeftButton:
            self._start = self._end = e.position().toPoint()
            self._owner._press()
            self.update()

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._end = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._start is not None:
            self._owner._release()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._owner._finish(None)


class RegionSelector(QObject):
    selected = Signal(tuple)  # (x, y, w, h) physical pixels
    cancelled = Signal()

    def __init__(self, cursor_fn: Callable[[], tuple[int, int]] = cursor_pos_physical):
        super().__init__()
        self._cursor = cursor_fn
        self._start: tuple[int, int] | None = None
        self.windows: list[_ScreenShade] = []

    def begin(self) -> None:
        self._finish_windows()
        self._start = None
        for screen in QGuiApplication.screens():
            win = _ScreenShade(self, screen.geometry())
            win.show()
            win.activateWindow()
            win.setFocus()
            self.windows.append(win)

    def _press(self) -> None:
        self._start = self._cursor()

    def _release(self) -> None:
        if self._start is None:
            return
        rect = normalize_rect(*self._start, *self._cursor())
        self._finish(rect if rect[2] >= MIN_SIZE and rect[3] >= MIN_SIZE else None)

    def _finish_windows(self) -> None:
        windows, self.windows = self.windows, []
        for w in windows:
            w.close()

    def _finish(self, rect: tuple[int, int, int, int] | None) -> None:
        self._finish_windows()
        if rect is None:
            self.cancelled.emit()
        else:
            self.selected.emit(rect)
