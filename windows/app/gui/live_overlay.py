"""Live overlays: click-through, excluded from capture, never covering the watched text."""
import html

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.config import Overlay as OverlayCfg
from app.gui.overlay import FONT, GAP, physical_to_logical
from app.gui.win32 import exclude_from_capture
from app.pipeline import Segment

LIVE_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
              | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)


def place_above(region: QRect, size: QSize, screen: QRect, gap: int = GAP) -> QPoint:
    """Spec §5.6: above the watched region by default, below when there is no room above."""
    x = max(screen.left(), min(region.left(), screen.right() + 1 - size.width()))
    above = region.top() - gap - size.height()
    if above >= screen.top():
        return QPoint(x, above)
    return QPoint(x, min(region.bottom() + 1 + gap, screen.bottom() + 1 - size.height()))


class LiveOverlay(QWidget):
    """Dialogue Live: translation shown just above the watched region; never takes the mouse."""

    def __init__(self, cfg: OverlayCfg, region: QRect, screen: QRect):
        super().__init__(None, LIVE_FLAGS)
        self.cfg = cfg
        self.region = region
        self.screen_rect = screen
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setFont(QFont(FONT, cfg.font_size))
        self.label.setStyleSheet("color: white;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self.label)
        self.setFixedWidth(max(min(region.width(), int(screen.width() * 0.9)), 240))
        self._shown_once = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 24, round(255 * self.cfg.opacity)))
        p.drawRoundedRect(self.rect(), 8, 8)

    def text(self) -> str:
        return self.label.text()

    def show_segments(self, segments: list[Segment]) -> None:
        parts = []
        for s in segments:
            if s.kind == "name":
                parts.append(f"<b>[{html.escape(s.source)}]</b>")
            else:
                parts.append(html.escape(s.translation or ""))
        if not parts:
            self.hide()
            return
        self.label.setText("<br>".join(parts))
        self.adjustSize()
        self.move(place_above(self.region, self.size(), self.screen_rect))
        self.show()
        if not self._shown_once:
            self._shown_once = True
            exclude_from_capture(int(self.winId()))


class AreaOverlay(QWidget):
    """Large-area Live: each tracked text block gets its translation drawn over it (click-through)."""

    def __init__(self, cfg: OverlayCfg, screen_geometry: QRect, dpr: float):
        super().__init__(None, LIVE_FLAGS)
        from app.gui.fullscreen import Block, block_rect, fit_text  # avoid an import cycle at module load

        self._Block, self._block_rect, self._fit_text = Block, block_rect, fit_text
        self.cfg = cfg
        self.screen_geometry = screen_geometry
        self.dpr = dpr
        self.blocks: dict[str, object] = {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(screen_geometry)
        self._shown_once = False

    def set_block(self, key: str, seg: Segment, origin: tuple[int, int]) -> None:
        r = physical_to_logical(self._block_rect(seg.box, origin), self.screen_geometry, self.dpr)
        r.translate(-self.screen_geometry.left(), -self.screen_geometry.top())
        if seg.kind == "name":
            self.blocks[key] = self._Block(r, seg, seg.source, 9, r.height())
        else:
            size, text, h = self._fit_text(seg.translation or "…", r.width(), r.height(), self.cfg.font_size)
            self.blocks[key] = self._Block(r, seg, text, size, h)
        self._refresh()

    def remove_block(self, key: str) -> None:
        if self.blocks.pop(key, None) is not None:
            self._refresh()

    def _refresh(self) -> None:
        if not self._shown_once:
            self._shown_once = True
            self.show()
            exclude_from_capture(int(self.winId()))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alpha = round(255 * self.cfg.opacity)
        for b in self.blocks.values():
            area = QRect(b.rect.left(), b.rect.top(), b.rect.width(), b.draw_height)
            p.setFont(QFont(FONT, b.font_size))
            if b.segment.kind == "name":
                p.setPen(QColor(255, 220, 140))
                p.drawText(area, Qt.AlignLeft | Qt.AlignVCenter, b.text)
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 20, 24, alpha))
            p.drawRoundedRect(area, 4, 4)
            p.setPen(Qt.white)
            p.drawText(area.adjusted(4, 4, -4, -4), Qt.TextWordWrap, b.text)
