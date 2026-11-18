import ctypes
from ctypes import wintypes

import pytest

from app.gui.hotkeys import WM_HOTKEY, HotkeyManager, parse_hotkey


def test_parse_basic():
    assert parse_hotkey("ctrl+alt+t") == (0x4000 | 2 | 1, 0x54)


def test_parse_spaces_case_function_key():
    assert parse_hotkey("Ctrl + Shift + F5") == (0x4000 | 2 | 4, 0x74)


def test_parse_digit_and_win():
    assert parse_hotkey("win+1") == (0x4000 | 8, 0x31)


@pytest.mark.parametrize("bad", ["alt", "ctrl+alt+ü", "", "ctrl+alt+t+y", "hyper+t"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse_hotkey(bad)


def _msg(message: int, wparam: int) -> ctypes.Array:
    msg = wintypes.MSG()
    msg.message = message
    msg.wParam = wparam
    return msg


def test_filter_emits_triggered_name(qtbot):
    mgr = HotkeyManager(register_fn=lambda *a: True, unregister_fn=lambda *a: True)
    assert mgr.register("translate_region", "ctrl+alt+t")
    msg = _msg(WM_HOTKEY, mgr.id_of("translate_region"))
    with qtbot.waitSignal(mgr.triggered, timeout=1000) as blocker:
        mgr.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
    assert blocker.args == ["translate_region"]


def test_other_messages_ignored(qtbot):
    mgr = HotkeyManager(register_fn=lambda *a: True, unregister_fn=lambda *a: True)
    mgr.register("x", "ctrl+alt+t")
    msg = _msg(0x0100, mgr.id_of("x"))
    with qtbot.assertNotEmitted(mgr.triggered):
        mgr.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))


def test_register_failure_returns_false():
    mgr = HotkeyManager(register_fn=lambda *a: False, unregister_fn=lambda *a: True)
    assert mgr.register("x", "ctrl+alt+t") is False


@pytest.mark.local
def test_real_double_registration_fails(qtbot):
    a, b = HotkeyManager(), HotkeyManager()
    try:
        assert a.register("x", "ctrl+alt+shift+f12")
        assert b.register("x", "ctrl+alt+shift+f12") is False
    finally:
        a.unregister_all()
        b.unregister_all()


@pytest.mark.local
def test_real_keypress_reaches_qt_filter(qtbot):
    user32 = ctypes.windll.user32
    mgr = HotkeyManager()
    try:
        assert mgr.register("probe", "ctrl+alt+shift+f12")
        with qtbot.waitSignal(mgr.triggered, timeout=3000) as blocker:
            keys = [0x11, 0x12, 0x10, 0x7B]  # ctrl, alt, shift, F12
            for k in keys:
                user32.keybd_event(k, 0, 0, 0)
            for k in reversed(keys):
                user32.keybd_event(k, 0, 2, 0)  # KEYEVENTF_KEYUP
        assert blocker.args == ["probe"]
    finally:
        mgr.unregister_all()


@pytest.mark.local
def test_hotkey_managers_from_earlier_tests_do_not_crash_later_windows():
    """Regression: managers garbage-collected while their native filter stayed installed crashed
    the next window show() (reproduced by running these three files together)."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    tests = Path(__file__).parent
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "not local", "-p", "no:cacheprovider",
         str(tests / "test_hotkeys.py"), str(tests / "test_models.py"), str(tests / "test_selector.py")],
        capture_output=True, cwd=tests.parents[1], env=dict(os.environ), timeout=300,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")[-800:]
