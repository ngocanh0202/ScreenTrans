"""Small Win32 helpers. Coordinates are physical pixels (Qt makes the process per-monitor DPI aware)."""
import ctypes
from ctypes import wintypes

WDA_EXCLUDEFROMCAPTURE = 0x11
MONITOR_DEFAULTTONEAREST = 2


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def cursor_pos_physical() -> tuple[int, int]:
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def monitor_rect_at(x: int, y: int) -> tuple[int, int, int, int]:
    """(left, top, width, height) of the monitor containing (x, y), physical pixels."""
    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    hmon = user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST)
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW(hmon, ctypes.byref(info))
    r = info.rcMonitor
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def exclude_from_capture(hwnd: int) -> bool:
    """Hide a window from screen capture (Windows 10 2004+), so the app never OCRs its own overlay."""
    try:
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), WDA_EXCLUDEFROMCAPTURE))
    except (AttributeError, OSError):
        return False
