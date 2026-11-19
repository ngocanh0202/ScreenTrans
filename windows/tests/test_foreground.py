import os

from app.gui import foreground as fg


class FakeApi:
    """Stands in for the Win32 calls foreground.py makes."""

    def __init__(self, windows, foreground):
        self.windows = windows  # hwnd -> dict(pid, exe, title, client, minimized, visible)
        self.fg = foreground

    def foreground(self):
        return self.fg

    def pid(self, hwnd):
        return self.windows[hwnd]["pid"]

    def exe(self, pid):
        return next(w["exe"] for w in self.windows.values() if w["pid"] == pid)

    def title(self, hwnd):
        return self.windows[hwnd]["title"]

    def client(self, hwnd):
        return self.windows[hwnd]["client"]

    def minimized(self, hwnd):
        return self.windows[hwnd]["minimized"]

    def top_windows(self):
        return [h for h, w in self.windows.items() if w.get("visible", True)]


WINDOWS = {
    1: {"pid": 10, "exe": r"C:\Games\Reverse1999\ReverseOne.EXE", "title": "Reverse: 1999",
        "client": (100, 50, 1280, 720), "minimized": False},
    2: {"pid": os.getpid(), "exe": r"C:\x\ScreenTrans.exe", "title": "ScreenTrans", "client": (0, 0, 10, 10),
        "minimized": False},
    3: {"pid": 10, "exe": r"C:\Games\Reverse1999\ReverseOne.EXE", "title": "tooltip", "client": (0, 0, 20, 20),
        "minimized": False},
}


def test_current_game_is_the_foreground_process_exe_in_lowercase():
    g = fg.current_game(FakeApi(WINDOWS, 1))
    assert (g.exe, g.title, g.client, g.minimized) == ("reverseone.exe", "Reverse: 1999", (100, 50, 1280, 720), False)


def test_our_own_window_is_not_a_game():
    assert fg.current_game(FakeApi(WINDOWS, 2)) is None
    assert fg.current_game(FakeApi(WINDOWS, 0)) is None


def test_game_window_finds_the_largest_window_of_that_exe():
    g = fg.game_window("reverseone.exe", FakeApi(WINDOWS, 2))
    assert g.client == (100, 50, 1280, 720)
    assert fg.game_window("other.exe", FakeApi(WINDOWS, 2)) is None


def test_m5_the_game_window_is_cached_between_ticks():
    class Counting(FakeApi):
        def __init__(self, *a):
            super().__init__(*a)
            self.enumerations = 0

        def top_windows(self):
            self.enumerations += 1
            return super().top_windows()

        def is_window(self, hwnd):
            return hwnd in self.windows

    api = Counting(WINDOWS, 2)
    cache = {}
    assert fg.game_window("reverseone.exe", api, cache).client == (100, 50, 1280, 720)
    assert fg.game_window("reverseone.exe", api, cache).client == (100, 50, 1280, 720)
    assert api.enumerations == 1
    del api.windows[1]
    assert fg.game_window("reverseone.exe", api, cache).client == (0, 0, 20, 20)  # gone: look again
    assert api.enumerations == 2
