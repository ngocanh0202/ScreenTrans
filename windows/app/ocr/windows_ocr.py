"""Windows.Media.Ocr through winocr, returning lines with boxes in source-image pixels."""
from PIL import Image

from app.ocr.base import INSTALL_HINT, Line, OcrUnavailable


def language_available(lang: str) -> bool:
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    return OcrEngine.try_create_from_language(Language(lang)) is not None


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    rgba = img.convert("RGBA")
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.getchannel("A"))
    return bg


class WindowsOcr:
    def __init__(self, lang: str = "en", min_height: int = 32):
        self.lang = lang
        self.min_height = min_height

    def recognize(self, img: Image.Image) -> list[Line]:
        import winocr

        img = _to_rgb(img)
        scale = 1.0
        if 0 < img.height < self.min_height:
            scale = self.min_height / img.height
            img = img.resize((round(img.width * scale), self.min_height), Image.LANCZOS)
        try:
            result = winocr.recognize_pil_sync(img, self.lang)
        except Exception as e:
            if not language_available(self.lang):
                raise OcrUnavailable(INSTALL_HINT) from e
            raise
        lines = []
        for line in result.get("lines") or []:
            rects = [w["bounding_rect"] for w in line.get("words") or []]
            if not rects:
                continue
            left = min(r["x"] for r in rects)
            top = min(r["y"] for r in rects)
            right = max(r["x"] + r["width"] for r in rects)
            bottom = max(r["y"] + r["height"] for r in rects)
            lines.append(Line(line["text"], left / scale, top / scale, (right - left) / scale, (bottom - top) / scale))
        return lines
