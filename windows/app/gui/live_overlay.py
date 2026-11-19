"""Live overlay (4b): each text block's translation drawn over it; click-through, excluded from capture.

Font size follows the source text (its OCR line height); colours are sampled from the game ("match" style)
or white on dark ("classic", or when sampling found no readable colours).
"""
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from app.config import Overlay as OverlayCfg
from app.gui.fullscreen import PAD, block_rect
from app.gui.overlay import FONT, physical_to_logical
from app.gui.win32 import exclude_from_capture
from app.live.style import BlockStyle

LIVE_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
              | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
MIN_PX = 11     # smallest readable size (logical px)
GROW = 1.5      # a translation may take 1.5x the source box height before the font shrinks
NAME_COLOR = QColor(255, 220, 140)
LIFT = 0.2      # translations start this much (x font size) above the source box: drawn from the box top + padding
                # they looked a little low; the bottom stays put so the source line is still covered


@dataclass
class LiveBlock:
    rect: QRect           # widget-local logical rect of the source text
    kind: str
    text: str
    px: int               # font pixel size (logical)
    draw_height: int
    fg: QColor
    bg: QColor
    angle: float = 0.0          # tilted text: drawn rotated by `angle` around `pivot`
    pivot: QPoint | None = None  # widget-local logical position of the OCR image origin


def _font(px: int) -> QFont:
    f = QFont(FONT)
    f.setPixelSize(max(1, px))
    return f


def fit_px(text: str, width: int, height: int, base_px: int, grow: bool = True) -> tuple[int, str, int]:
    """The whole translation, never cut: (px, text, drawn height). grow: the source size, the box as tall as the
    text needs; otherwise the largest size down to MIN_PX that fits height*GROW, and at MIN_PX it grows anyway."""
    inner = max(width - 2 * PAD, 10)

    def needed(px: int) -> int:
        fm = QFontMetrics(_font(px))
        return fm.boundingRect(QRect(0, 0, inner, 100000), Qt.TextWordWrap, text).height() + 2 * PAD

    base = max(base_px, MIN_PX)
    if not grow:
        for px in range(base, MIN_PX, -1):
            h = needed(px)
            if h <= int(height * GROW):
                return px, text, max(h, height)
        base = MIN_PX
    return base, text, max(needed(base), height)


class AreaOverlay(QWidget):
    """Covers one screen; blocks are keyed so a growing text block is redrawn in place."""

    def __init__(self, cfg: OverlayCfg, screen_geometry: QRect, dpr: float):
        super().__init__(None, LIVE_FLAGS)
        self.cfg = cfg
        self.screen_geometry = screen_geometry
        self.dpr = dpr
        self.blocks: dict[str, LiveBlock] = {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(screen_geometry)
        self._shown_once = False

    def set_block(self, key: str, text: str, box: tuple[float, float, float, float], origin: tuple[int, int],
                  kind: str = "text", font_px: float | None = None, colors: BlockStyle | None = None,
                  angle: float = 0.0) -> None:
        """`box`: left, top, right, bottom in the captured image; `origin`: its physical top-left;
        `font_px`: the source text size in physical px (None: the configured size)."""
        r = physical_to_logical(block_rect(box, origin), self.screen_geometry, self.dpr)
        r.translate(-self.screen_geometry.left(), -self.screen_geometry.top())
        base = round((font_px / self.dpr if font_px else self.cfg.font_size * 4 / 3) * self.cfg.text_scale)  # pt -> px
        if colors is not None:
            fg, bg = QColor(*colors.text), QColor(*colors.bg)  # opaque: the translation replaces the source
        else:
            fg, bg = QColor(255, 255, 255), QColor(20, 20, 24, round(255 * self.cfg.opacity))
        pivot = physical_to_logical((origin[0], origin[1], 0, 0), self.screen_geometry, self.dpr).topLeft()
        pivot -= self.screen_geometry.topLeft()
        if kind == "name":
            fg = fg if colors is not None else NAME_COLOR
            self.blocks[key] = LiveBlock(r, kind, text, max(base, MIN_PX), r.height(), fg, bg, angle, pivot)
        else:
            px, fitted, h = fit_px(text, r.width(), r.height(), base, grow=self.cfg.long_text != "shrink")
            lift = min(round(px * LIFT), r.top()) if not angle else round(px * LIFT)  # never above the screen
            r.setTop(r.top() - lift)
            h += lift
            if not angle and r.top() + h > self.height():  # would run off the bottom: move up, not past the top
                r.moveTop(max(0, self.height() - h))
            self.blocks[key] = LiveBlock(r, kind, fitted, px, h, fg, bg, angle, pivot)
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
        for b in self.blocks.values():
            area = QRect(b.rect.left(), b.rect.top(), b.rect.width(), b.draw_height)
            if b.angle and b.pivot is not None:  # tilted text: draw in its frame, rotated around the image origin
                p.save()
                p.translate(b.pivot)
                p.rotate(b.angle)
                area.translate(-b.pivot)
            p.setFont(_font(b.px))
            p.setPen(Qt.NoPen)
            p.setBrush(b.bg)
            p.drawRoundedRect(area, 3, 3)
            p.setPen(b.fg)
            if b.kind == "name":
                p.drawText(area.adjusted(PAD, 0, -PAD, 0), Qt.AlignLeft | Qt.AlignVCenter, b.text)
            else:
                p.drawText(area.adjusted(PAD, PAD, -PAD, -PAD), Qt.TextWordWrap, b.text)
            if b.angle and b.pivot is not None:
                p.restore()
