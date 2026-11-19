"""OCR interface shared by engines."""
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

INSTALL_HINT = (
    "Windows OCR cannot use English. Install it: Settings > Time & language > "
    "Language & region > Add a language > English (United States), including the "
    "'Optical character recognition' feature."
)


class OcrUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Line:
    text: str
    left: float
    top: float
    width: float
    height: float
    angle: float = 0.0  # degrees, clockwise; the box is in the frame rotated by -angle (see ocr/deskew.py)

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height


class OcrEngine(Protocol):
    def recognize(self, img: Image.Image) -> list[Line]: ...
