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


def fit_px(text: str, width: int, height: int, base_px: int, room: int | None = None) -> tuple[int, str, int]:
    """Largest pixel size from base_px down to MIN_PX whose wrapped text fits width x limit; else MIN_PX
    with trailing words dropped and an ellipsis. Returns (px, text, drawn height). limit = height*GROW, or
    with `room` (space down to the screen bottom) up to 3x the height or 40% of the room, never past it."""
    limit = int(height * GROW) if room is None else int(min(room, max(height * 3, height + room * 0.4)))
    inner = max(width - 2 * PAD, 10)

    def needed(px: int, t: str) -> int:
        fm = QFontMetrics(_font(px))
        return fm.boundingRect(QRect(0, 0, inner, 100000), Qt.TextWordWrap, t).height() + 2 * PAD

    for px in range(max(base_px, MIN_PX), MIN_PX - 1, -1):
        h = needed(px, text)
        if h <= limit:
            return px, text, max(h, height)
    words = text.split()
    while len(words) > 1 and needed(MIN_PX, " ".join(words) + "…") > limit:
        words.pop()
    return MIN_PX, " ".join(words) + "…", limit


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
        base = round(font_px / self.dpr) if font_px else round(self.cfg.font_size * 4 / 3)  # pt -> px
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
            room = self.height() - r.top() if self.cfg.long_text != "shrink" and not angle else None
            px, fitted, h = fit_px(text, r.width(), r.height(), base, room if room and room > r.height() else None)
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
