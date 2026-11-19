"""The OCR engines this platform offers (settings window "Bộ OCR"), per game in the profile."""
import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class Engine:
    name: str
    label: str
    note: str


WINDOWS = [
    Engine("windows", "Windows OCR", "Nhanh (~30 ms), có sẵn trong Windows. Mặc định."),
    Engine("rapid", "RapidOCR (PaddleOCR) — thử nghiệm",
           "Chậm (~5 giây mỗi ảnh): chỉ dùng cho dịch 1 lần; tự động dịch vẫn dùng Windows OCR."),
]
_IMPORTS = {"rapid": "rapidocr_onnxruntime"}


def available(name: str) -> bool:
    if name == "windows":
        return True
    module = _IMPORTS.get(name)
    return module is not None and importlib.util.find_spec(module) is not None


def create(name: str):
    if name == "rapid":
        from app.ocr.rapid import RapidOcr

        return RapidOcr()
    from app.ocr.windows_ocr import WindowsOcr

    return WindowsOcr()
