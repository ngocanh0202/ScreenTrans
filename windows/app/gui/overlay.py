"""One-shot result window shown next to the selected region."""
import html

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QTextDocument
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.config import Overlay as OverlayCfg
from app.gui.win32 import exclude_from_capture
from app.pipeline import Segment

GAP = 6
MIN_WIDTH = 420
FONT = "Segoe UI"


def place_overlay(region: QRect, size: QSize, screen: QRect, gap: int = GAP) -> QPoint:
    """Below the region (left-aligned, clamped to the screen); above if the bottom overflows."""
    x = min(max(region.left(), screen.left()), screen.right() + 1 - size.width())
    x = max(x, screen.left())
    below = region.bottom() + 1 + gap
    if below + size.height() <= screen.bottom() + 1:
        return QPoint(x, below)
    above = region.top() - gap - size.height()
    if above >= screen.top():
        return QPoint(x, above)
    return QPoint(x, screen.bottom() + 1 - size.height())


def physical_to_logical(rect_phys: tuple[int, int, int, int], screen_geometry: QRect, dpr: float) -> QRect:
    """Qt keeps each screen's native origin; distances inside the screen are divided by its DPR."""
    ox, oy = screen_geometry.left(), screen_geometry.top()
    x, y, w, h = rect_phys
    return QRect(round(ox + (x - ox) / dpr), round(oy + (y - oy) / dpr), round(w / dpr), round(h / dpr))


class ResultOverlay(QWidget):
    edit_requested = Signal()  # "Sửa": correct this translation

    def __init__(self, cfg: OverlayCfg):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.cfg = cfg
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._translations: list[str] = []
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        font = QFont(FONT, cfg.font_size)
        self.label.setFont(font)
        self.label.setStyleSheet("color: white;")
        self.copy_button = QPushButton("Copy")
        self.copy_button.setFont(QFont(FONT, 9))
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.setStyleSheet(
            "QPushButton { color: white; background: rgba(255,255,255,40); border: none; padding: 3px 10px; }"
            "QPushButton:disabled { color: rgba(255,255,255,90); }")
        self.copy_button.clicked.connect(self._copy)
        self.edit_button = QPushButton("Sửa")
        self.edit_button.setFont(QFont(FONT, 9))
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setStyleSheet(self.copy_button.styleSheet())
        self.edit_button.clicked.connect(self.edit_requested.emit)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.copy_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(self.label)
        layout.addLayout(buttons)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 24, round(255 * self.cfg.opacity)))
        p.drawRoundedRect(self.rect(), 8, 8)

    def text(self) -> str:
        """Plain text currently shown (for tests and accessibility)."""
        d = QTextDocument()
        d.setHtml(self.label.text())
        return d.toPlainText()

    def _set(self, html_text: str, can_copy: bool) -> None:
        self.label.setText(html_text)
        self.copy_button.setEnabled(can_copy)
        self.edit_button.setEnabled(can_copy)
        self.adjustSize()

    def show_loading(self, text: str) -> None:
        self._translations = []
        self._set(f"<i>{html.escape(text)}</i>", False)

    def show_error(self, text: str) -> None:
        self._translations = []
        self._set(f"<span style='color:#ff9a9a'>{html.escape(text)}</span>", False)

    def show_segments(self, segments: list[Segment], show_source: bool) -> None:
        parts = []
        self._translations = []
        for s in segments:
            if s.kind == "name":
                parts.append(f"<b>[{html.escape(s.source)}]</b>")
                continue
            if show_source:
                parts.append(f"<span style='color:#b8b8b8'>{html.escape(s.source)}</span>")
            parts.append(html.escape(s.translation or ""))
            self._translations.append(s.translation or "")
        self._set("<br>".join(parts) if parts else "<i>(không tìm thấy chữ)</i>", bool(self._translations))

    def present(self, region: QRect, screen: QRect) -> None:
        """Size to content (at least the region / MIN_WIDTH, at most 90% of the screen) and show."""
        width = min(max(region.width(), MIN_WIDTH), int(screen.width() * 0.9))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(place_overlay(region, self.size(), screen))
        self.show()
        exclude_from_capture(int(self.winId()))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText("\n".join(self._translations))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)
