"""Screen capture of a region in physical pixels of the virtual screen (all monitors)."""
import ctypes

from PIL import Image

_dpi_done = False


def enable_dpi_awareness() -> None:
    """Per-monitor DPI awareness so coordinates match physical pixels at 125%/150% scaling."""
    global _dpi_done
    if _dpi_done:
        return
    _dpi_done = True
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def parse_region(s: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Region must be 'x,y,w,h', got {s!r}")
    try:
        x, y, w, h = (int(p) for p in parts)
    except ValueError:
        raise ValueError(f"Region values must be integers, got {s!r}") from None
    if w <= 0 or h <= 0:
        raise ValueError(f"Region width and height must be positive, got {s!r}")
    return x, y, w, h


def capture_region(left: int, top: int, width: int, height: int) -> Image.Image:
    import mss

    enable_dpi_awareness()
    with mss.MSS() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
