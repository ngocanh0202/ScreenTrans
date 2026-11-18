"""Live overlay (4b): each text block's translation drawn over it; click-through, excluded from capture."""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from app.config import Overlay as OverlayCfg
from app.gui.fullscreen import MIN_FONT, PAD, Block, block_rect, fit_text
from app.gui.overlay import FONT, physical_to_logical
from app.gui.win32 import exclude_from_capture
from app.pipeline import Segment

LIVE_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
              | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)


class AreaOverlay(QWidget):
    """Covers one screen; blocks are keyed so a growing text block is redrawn in place."""

    def __init__(self, cfg: OverlayCfg, screen_geometry: QRect, dpr: float):
        super().__init__(None, LIVE_FLAGS)
        self.cfg = cfg
        self.screen_geometry = screen_geometry
        self.dpr = dpr
        self.blocks: dict[str, Block] = {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(screen_geometry)
        self._shown_once = False

    def set_block(self, key: str, text: str, box: tuple[float, float, float, float], origin: tuple[int, int],
                  kind: str = "text") -> None:
        """`box`: left, top, right, bottom in the captured image; `origin`: its physical top-left."""
        r = physical_to_logical(block_rect(box, origin), self.screen_geometry, self.dpr)
        r.translate(-self.screen_geometry.left(), -self.screen_geometry.top())
        seg = Segment(kind, text, None if kind == "name" else text, box)
        if kind == "name":
            self.blocks[key] = Block(r, seg, text, MIN_FONT, r.height())
        else:
            size, fitted, h = fit_text(text, r.width(), r.height(), self.cfg.font_size)
            self.blocks[key] = Block(r, seg, fitted, size, h)
        self._refresh()

    def remove_block(self, key: str) -> None:
        if self.blocks.pop(key, None) is not None:
            self._refresh()

    def _refresh(self) -> None:
        if not self._shown_once:
            self._shown_once = True
            exclude_from_capture(int(self.winId()))  # before the first paint reaches the screen
            self.show()
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
            p.drawText(area.adjusted(PAD, PAD, -PAD, -PAD), Qt.TextWordWrap, b.text)
