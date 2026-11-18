"""Which game is running: the foreground window's process (spec §5.5), and where its client area is.

Physical pixels (the process is per-monitor DPI aware). The Win32 calls sit behind `Win32Api` so the
selection logic is testable with a fake.
"""
import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath


@dataclass
class GameWindow:
    hwnd: int
    exe: str            # lower-case file name, e.g. "reverseone.exe" (the profile id)
    title: str
    client: tuple[int, int, int, int]  # x, y, w, h of the client area
    minimized: bool


class Win32Api:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self):
        self.u = ctypes.windll.user32
        self.k = ctypes.windll.kernel32
        self.u.GetForegroundWindow.restype = wintypes.HWND

    def foreground(self) -> int:
        return self.u.GetForegroundWindow() or 0

    def pid(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        self.u.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return pid.value

    def exe(self, pid: int) -> str:
        h = self.k.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            ok = self.k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            return buf.value if ok else ""
        finally:
            self.k.CloseHandle(h)

    def title(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(512)
        self.u.GetWindowTextW(wintypes.HWND(hwnd), buf, len(buf))
        return buf.value

    def client(self, hwnd: int) -> tuple[int, int, int, int]:
        r = wintypes.RECT()
        self.u.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(r))
        pt = wintypes.POINT(0, 0)
        self.u.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
        return pt.x, pt.y, r.right - r.left, r.bottom - r.top

    def minimized(self, hwnd: int) -> bool:
        return bool(self.u.IsIconic(wintypes.HWND(hwnd)))

    def top_windows(self) -> list[int]:
        found: list[int] = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            if self.u.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True

        self.u.EnumWindows(proc(cb), 0)
        return found


def _info(api, hwnd: int) -> GameWindow | None:
    pid = api.pid(hwnd)
    if not pid or pid == os.getpid():
        return None
    path = api.exe(pid)
    if not path:
        return None
    return GameWindow(hwnd, PureWindowsPath(path).name.lower(), api.title(hwnd), tuple(api.client(hwnd)),
                      api.minimized(hwnd))


def current_game(api=None) -> GameWindow | None:
    """The foreground window's process, unless it is ScreenTrans itself (or nothing)."""
    api = api or Win32Api()
    hwnd = api.foreground()
    return _info(api, hwnd) if hwnd else None


def game_window(exe: str, api=None) -> GameWindow | None:
    """The largest visible top-level window of `exe` (a game may also own small tool windows)."""
    api = api or Win32Api()
    best = None
    for hwnd in api.top_windows():
        info = _info(api, hwnd)
        if info is None or info.exe != exe:
            continue
        if best is None or info.client[2] * info.client[3] > best.client[2] * best.client[3]:
            best = info
    return best
