"""Pure helpers for the OCR spike: character error rate and image preparation."""
from PIL import Image


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    ref, hyp = _normalize(ref), _normalize(hyp)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def prepare_image(img: Image.Image, min_height: int = 32) -> Image.Image:
    if img.mode != "RGB":
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        img = bg
    if img.height < min_height:
        scale = min_height / img.height
        img = img.resize((round(img.width * scale), min_height), Image.LANCZOS)
    return img
