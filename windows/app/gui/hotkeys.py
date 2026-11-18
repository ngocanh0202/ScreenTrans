"""System-wide hotkeys via Win32 RegisterHotKey, delivered through Qt's native event filter."""
import ctypes
import itertools
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_MODS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN}
_IDS = itertools.count(0xA000)  # unique per process so several managers never clash


def _vk(key: str) -> int:
    if len(key) == 1 and ("a" <= key <= "z" or "0" <= key <= "9"):
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        return 0x70 + int(key[1:]) - 1
    raise ValueError(f"Unsupported key {key!r}")


def parse_hotkey(s: str) -> tuple[int, int]:
    """'ctrl+alt+t' -> (modifiers | MOD_NOREPEAT, virtual-key code)."""
    parts = [p.strip().lower() for p in s.split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey")
    *mods, key = parts
    if key in _MODS:
        raise ValueError(f"Hotkey {s!r} has no key, only modifiers")
    flags = MOD_NOREPEAT
    for m in mods:
        if m not in _MODS:
            raise ValueError(f"Unknown modifier {m!r} in {s!r}")
        flags |= _MODS[m]
    return flags, _vk(key)


def _win_register(hotkey_id: int, mods: int, vk: int) -> bool:
    return bool(ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mods, vk))


def _win_unregister(hotkey_id: int) -> bool:
    return bool(ctypes.windll.user32.UnregisterHotKey(None, hotkey_id))


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "HotkeyManager"):
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):
        return self._owner.nativeEventFilter(event_type, message)


class HotkeyManager(QObject):
    triggered = Signal(str)

    def __init__(
        self,
        register_fn: Callable[[int, int, int], bool] = _win_register,
        unregister_fn: Callable[[int], bool] = _win_unregister,
    ):
        super().__init__()
        self._register_fn = register_fn
        self._unregister_fn = unregister_fn
        self._ids: dict[str, int] = {}
        self._names: dict[int, str] = {}
        self._filter = _Filter(self)
        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    def register(self, name: str, combo: str) -> bool:
        mods, vk = parse_hotkey(combo)
        hotkey_id = next(_IDS)
        if not self._register_fn(hotkey_id, mods, vk):
            return False
        self._ids[name] = hotkey_id
        self._names[hotkey_id] = name
        return True

    def id_of(self, name: str) -> int:
        return self._ids[name]

    def unregister_all(self) -> None:
        for hotkey_id in list(self._names):
            self._unregister_fn(hotkey_id)
        self._ids.clear()
        self._names.clear()

    def nativeEventFilter(self, event_type, message) -> tuple[bool, int]:
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam in self._names:
            self.triggered.emit(self._names[msg.wParam])
            return True, 0
        return False, 0
