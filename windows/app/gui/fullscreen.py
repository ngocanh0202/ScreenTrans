"""Full-screen mode: translations drawn over each text block of the captured monitor."""
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from app.config import Overlay as OverlayCfg
from app.gui.overlay import FONT, ResultOverlay, physical_to_logical
from app.gui.win32 import exclude_from_capture
from app.pipeline import Segment

MIN_FONT = 9
GROW = 1.5   # a block may grow to 150% of the original text height before eliding
PAD = 4


def block_rect(box: tuple[float, float, float, float], origin: tuple[int, int]) -> tuple[int, int, int, int]:
    """Segment box (left, top, right, bottom in image pixels) + capture origin -> physical (x, y, w, h)."""
    left, top, right, bottom = box
    return round(origin[0] + left), round(origin[1] + top), round(right - left), round(bottom - top)


def fit_text(text: str, width: int, height: int, base: int) -> tuple[int, str, int]:
    """Largest font (base..MIN_FONT) whose wrapped text fits width x height*GROW; else MIN_FONT and
    drop trailing words with an ellipsis. Returns (font size, text, drawn height)."""
    limit = int(height * GROW)
    inner = max(width - 2 * PAD, 10)

    def needed(size: int, t: str) -> int:
        fm = QFontMetrics(QFont(FONT, size))
        return fm.boundingRect(QRect(0, 0, inner, 100000), Qt.TextWordWrap, t).height() + 2 * PAD

    for size in range(base, MIN_FONT - 1, -1):
        h = needed(size, text)
        if h <= limit:
            return size, text, max(h, height)
    words = text.split()
    while len(words) > 1 and needed(MIN_FONT, " ".join(words) + "…") > limit:
        words.pop()
    return MIN_FONT, " ".join(words) + "…", limit


@dataclass
class Block:
    rect: QRect          # widget-local logical coordinates of the source text
    segment: Segment
    text: str
    font_size: int
    draw_height: int
    angle: float = 0.0           # tilted text: drawn rotated by `angle` around `pivot`
    pivot: QPoint | None = None


class FullscreenOverlay(QWidget):
    def __init__(self, cfg: OverlayCfg, screen_geometry: QRect, dpr: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.cfg = cfg
        self.screen_geometry = screen_geometry
        self.dpr = dpr
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(screen_geometry)
        self.blocks: list[Block] = []
        self.translating = True
        self.detail: ResultOverlay | None = None

    def present(self) -> None:
        self.show()
        self.activateWindow()
        self.setFocus()
        exclude_from_capture(int(self.winId()))

    def add_segment(self, seg: Segment, origin: tuple[int, int]) -> None:
        r = physical_to_logical(block_rect(seg.box, origin), self.screen_geometry, self.dpr)
        r.translate(-self.screen_geometry.left(), -self.screen_geometry.top())
        pivot = physical_to_logical((origin[0], origin[1], 0, 0), self.screen_geometry, self.dpr).topLeft()
        pivot -= self.screen_geometry.topLeft()
        angle = getattr(seg, "angle", 0.0)
        if seg.kind == "name":
            self.blocks.append(Block(r, seg, seg.source, MIN_FONT, r.height(), angle, pivot))
        else:
            size, text, h = fit_text(seg.translation or "", r.width(), r.height(), self.cfg.font_size)
            self.blocks.append(Block(r, seg, text, size, h, angle, pivot))
        self.update()

    def finish(self) -> None:
        self.translating = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alpha = round(255 * self.cfg.opacity)
        for b in self.blocks:
            area = QRect(b.rect.left(), b.rect.top(), b.rect.width(), b.draw_height)
            tilted = bool(b.angle) and b.pivot is not None
            if tilted:  # tilted text: draw in its frame, rotated around the image origin
                p.save()
                p.translate(b.pivot)
                p.rotate(b.angle)
                area.translate(-b.pivot)
            p.setFont(QFont(FONT, b.font_size))
            if b.segment.kind == "name":
                p.setPen(QColor(255, 220, 140))
                p.drawText(area, Qt.AlignLeft | Qt.AlignVCenter, b.text)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(20, 20, 24, alpha))
                p.drawRoundedRect(area, 4, 4)
                p.setPen(Qt.white)
                p.drawText(area.adjusted(PAD, PAD, -PAD, -PAD), Qt.TextWordWrap, b.text)
            if tilted:
                p.restore()
        if self.translating:
            p.setFont(QFont(FONT, 10))
            chip = QRect(self.width() - 140, 12, 128, 26)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 20, 24, 220))
            p.drawRoundedRect(chip, 6, 6)
            p.setPen(Qt.white)
            p.drawText(chip, Qt.AlignCenter, "Đang dịch…")

    def _block_at(self, pos) -> Block | None:
        for b in reversed(self.blocks):
            p = pos
            if b.angle and b.pivot is not None:  # into the block's tilted frame
                from app.ocr.deskew import rotate_point

                x, y = rotate_point(pos.x() - b.pivot.x(), pos.y() - b.pivot.y(), b.angle)
                p = QPoint(round(b.pivot.x() + x), round(b.pivot.y() + y))
            if QRect(b.rect.left(), b.rect.top(), b.rect.width(), b.draw_height).contains(p):
                return b
        return None

    def _screen_rect(self, b: Block) -> QRect:
        """Where the block is drawn (the bounds of the rotated box for tilted text), widget-local."""
        if not (b.angle and b.pivot is not None):
            return QRect(b.rect)
        from app.ocr.deskew import bounds

        px, py = b.pivot.x(), b.pivot.y()
        l, t, r, bt = bounds((b.rect.left() - px, b.rect.top() - py, b.rect.right() - px, b.rect.top() - py + b.draw_height),
                             b.angle)
        return QRect(round(px + l), round(py + t), round(r - l), round(bt - t))

    def mousePressEvent(self, e):
        block = self._block_at(e.position().toPoint())
        if block is None or block.segment.kind == "name":
            self.close()
            return
        if self.detail is not None:
            self.detail.close()
        self.detail = ResultOverlay(self.cfg)
        self.detail.show_segments([block.segment], show_source=True)
        local = self._screen_rect(block)
        local.translate(self.screen_geometry.left(), self.screen_geometry.top())
        self.detail.present(local, self.screen_geometry)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.detail is not None:
            self.detail.close()
        super().closeEvent(e)
