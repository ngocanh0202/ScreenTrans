"""API keys of the remote translation engines, encrypted for the current Windows user (DPAPI)."""
import ctypes
import json
from ctypes import wintypes
from pathlib import Path


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _crypt(fn, data: bytes) -> bytes:
    out = _Blob()
    if not fn(ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _crypt(ctypes.windll.crypt32.CryptProtectData, data)


def unprotect(data: bytes) -> bytes:
    return _crypt(ctypes.windll.crypt32.CryptUnprotectData, data)


class KeyStore:
    """data_dir/keys.bin = DPAPI({engine: key}); unreadable -> no keys."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "keys.bin"

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(unprotect(self.path.read_bytes()).decode("utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}

    def get(self, engine: str) -> str:
        return self._load().get(engine, "")

    def set(self, engine: str, key: str) -> None:
        keys = self._load()
        key = (key or "").strip()
        if key:
            keys[engine] = key
        else:
            keys.pop(engine, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(protect(json.dumps(keys).encode("utf-8")))
        tmp.replace(self.path)
