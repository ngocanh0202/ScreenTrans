"""OCR engines compared in spike A. Heavy imports stay inside functions."""
from PIL import Image

from spikes.ocr.metrics import prepare_image

INSTALL_HINT = (
    "Windows OCR cannot use English. Install it: Settings > Time & language > "
    "Language & region > Add a language > English (United States), with the "
    "'Optical character recognition' feature."
)


class OcrEngineUnavailable(Exception):
    pass


def windows_ocr(img: Image.Image) -> str:
    import winocr

    img = prepare_image(img)
    try:
        result = winocr.recognize_pil_sync(img, "en")
    except Exception as e:  # winrt raises generic errors when the language is missing
        raise OcrEngineUnavailable(f"{INSTALL_HINT} ({e})") from e
    lines = result.get("lines") or []
    return "\n".join(line["text"] for line in lines)


_rapid = None


def rapid_ocr(img: Image.Image) -> str:
    global _rapid
    import numpy as np

    if _rapid is None:
        from rapidocr_onnxruntime import RapidOCR

        _rapid = RapidOCR()
    result, _ = _rapid(np.array(prepare_image(img)))
    if not result:
        return ""
    boxes = []
    for box, text, _score in result:
        ys = [pt[1] for pt in box]
        boxes.append((min(ys), max(ys), min(pt[0] for pt in box), text))
    boxes.sort()
    lines: list[list[tuple]] = []
    for top, bottom, left, text in boxes:
        center = (top + bottom) / 2
        if lines:
            ltop, lbottom = lines[-1][0][0], lines[-1][0][1]
            if ltop <= center <= lbottom:
                lines[-1].append((top, bottom, left, text))
                continue
        lines.append([(top, bottom, left, text)])
    return "\n".join(" ".join(t for *_, t in sorted(line, key=lambda b: b[2])) for line in lines)
