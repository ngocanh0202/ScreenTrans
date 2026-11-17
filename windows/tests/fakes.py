"""Test doubles."""
from typing import Callable

from PIL import Image

from app.ocr.base import Line


class FakeTranslator:
    def __init__(self, fn: Callable[[str], str], model_id: str = "fake"):
        self.fn = fn
        self.model_id = model_id
        self.calls: list[list[str]] = []

    def translate(self, texts: list[str]) -> list[str]:
        self.calls.append(list(texts))
        return [self.fn(t) if t.strip() else "" for t in texts]


class FakeOcr:
    def __init__(self, lines: list[Line]):
        self.lines = lines

    def recognize(self, img: Image.Image) -> list[Line]:
        return list(self.lines)
