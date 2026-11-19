from PIL import Image
from PySide6.QtCore import QObject, Signal

from app.config import Config
from app.gui.worker import Job
from app.pipeline import Segment


class FakeWorker(QObject):
    ready = Signal()
    failed = Signal(str)
    progress = Signal(int, int)
    job_started = Signal(int)
    segment = Signal(int, object)
    job_done = Signal(int, object)
    job_failed = Signal(int, str)
    ocr_done = Signal(int, object)
    partial = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.jobs: list[Job] = []
        self.all_jobs: list[Job] = []

    def submit(self, job):
        self.all_jobs.append(job)
        if job.mode not in ("set_game", "correct"):  # control jobs: see all_jobs
            self.jobs.append(job)


class FakeThread:
    def __init__(self):
        self.stopped = False

    def quit(self):
        self.stopped = True

    def wait(self, ms=0):
        return True


class WorkerFactory:
    def __init__(self):
        self.workers: list[FakeWorker] = []

    def __call__(self, pipeline_factory, connect=None):
        w = FakeWorker()
        if connect:
            connect(w)
        self.workers.append(w)
        return FakeThread(), w


class FakeHotkeys(QObject):
    triggered = Signal(str)

    def __init__(self, ok=True):
        super().__init__()
        self.ok = ok
        self.registered = []

    def register(self, name, combo):
        self.registered.append((name, combo))
        return self.ok

    def close(self):
        pass


class FakeSelector(QObject):
    selected = Signal(tuple)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.begun = 0

    def begin(self):
        self.begun += 1


class Foreground:
    """Fake foreground-window lookup: `.game` is what current_game() returns; windows by exe for game_window()."""

    def __init__(self):
        self.game = None
        self.windows = {}

    def current(self):
        return self.game

    def window(self, exe):
        return self.windows.get(exe)


def game(exe="game.exe", client=(0, 0, 1920, 1080), title="Game", minimized=False):
    from app.gui.foreground import GameWindow

    return GameWindow(1, exe, title, client, minimized)


def _app(qtbot, ok=True, tmp_path=None, fg=None):
    from app.main import TrayApp

    cfg = Config()
    if tmp_path is not None:
        cfg.paths.data_dir = str(tmp_path)
    factory, hotkeys, selector = WorkerFactory(), FakeHotkeys(ok), FakeSelector()
    captures = []

    def capture(x, y, w, h):
        captures.append((x, y, w, h))
        return Image.new("RGB", (max(w, 1), max(h, 1)))

    fg = fg or Foreground()
    app = TrayApp(cfg, worker_factory=factory, hotkeys=hotkeys, selector=selector, capture=capture,
                  monitor_at=lambda x, y: (0, 0, 1920, 1080), cursor=lambda: (500, 500), capture_delay_ms=0,
                  foreground=fg.current, window_of=fg.window, timers=False)
    app.start()
    return app, factory, hotkeys, selector, captures


SEGS = [Segment("name", "Druvis III", None, (0, 0, 10, 10)),
        Segment("text", "Hello.", "Xin chào.", (0, 20, 100, 40))]


def test_registers_both_hotkeys(qtbot):
    _, _, hotkeys, _, _ = _app(qtbot)
    assert [n for n, _ in hotkeys.registered] == ["translate_region", "translate_fullscreen", "toggle_live", "edit_last"]


def test_region_flow_loading_then_result(qtbot):
    app, factory, hotkeys, selector, captures = _app(qtbot)
    hotkeys.triggered.emit("translate_region")
    assert selector.begun == 1
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: bool(factory.workers[0].jobs), timeout=2000)
    job = factory.workers[0].jobs[0]
    assert job.mode == "region" and captures == [(10, 10, 200, 100)]
    assert "Đang tải model…" in app.region_overlay.text()
    factory.workers[0].ready.emit()
    factory.workers[0].job_done.emit(job.id, SEGS)
    assert "[Druvis III]" in app.region_overlay.text() and "Xin chào." in app.region_overlay.text()


def test_stale_job_result_is_ignored(qtbot):
    app, factory, hotkeys, selector, _ = _app(qtbot)
    factory.workers[0].ready.emit()
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: len(factory.workers[0].jobs) == 1, timeout=2000)
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((20, 20, 200, 100))
    qtbot.waitUntil(lambda: len(factory.workers[0].jobs) == 2, timeout=2000)
    first, second = factory.workers[0].jobs
    factory.workers[0].job_done.emit(first.id, SEGS)
    assert "Xin chào." not in app.region_overlay.text()
    factory.workers[0].job_done.emit(second.id, SEGS)
    assert "Xin chào." in app.region_overlay.text()


def test_fullscreen_flow(qtbot):
    app, factory, hotkeys, _, captures = _app(qtbot)
    factory.workers[0].ready.emit()
    hotkeys.triggered.emit("translate_fullscreen")
    qtbot.waitUntil(lambda: bool(factory.workers[0].jobs), timeout=2000)
    job = factory.workers[0].jobs[0]
    assert job.mode == "fullscreen" and job.origin == (0, 0) and captures == [(0, 0, 1920, 1080)]
    factory.workers[0].segment.emit(job.id, SEGS[1])
    assert len(app.fullscreen_overlay.blocks) == 1 and app.fullscreen_overlay.translating
    factory.workers[0].job_done.emit(job.id, SEGS)
    assert not app.fullscreen_overlay.translating


def test_worker_failure_offers_retry(qtbot):
    app, factory, _, _, _ = _app(qtbot)
    factory.workers[0].failed.emit("No translation model in X")
    assert app.retry_action.isVisible() and "Lỗi" in app.status_action.text()
    app.retry_action.trigger()
    assert len(factory.workers) == 2


def test_job_failure_shows_error(qtbot):
    app, factory, hotkeys, selector, _ = _app(qtbot)
    factory.workers[0].ready.emit()
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: bool(factory.workers[0].jobs), timeout=2000)
    factory.workers[0].job_failed.emit(factory.workers[0].jobs[0].id, "boom")
    assert "boom" in app.region_overlay.text()


def test_switch_model_restarts_worker(qtbot):
    app, factory, _, _, _ = _app(qtbot)
    app.model_actions["opus-mt-en-vi"].trigger()
    assert app.config.translator.model == "opus-mt-en-vi" and len(factory.workers) == 2


def test_progress_updates_status(qtbot):
    app, factory, _, _, _ = _app(qtbot)
    factory.workers[0].progress.emit(120_000_000, 439_000_000)
    assert "120/439 MB" in app.status_action.text()
    factory.workers[0].ready.emit()
    assert "Sẵn sàng" in app.status_action.text()


def test_hotkey_failure_notifies(qtbot):
    app, _, _, _, _ = _app(qtbot, ok=False)
    assert "Ctrl+Alt+T" in app.last_message and "Ctrl+Alt+F" in app.last_message


def test_self_test(capsys):
    from app.main import main

    assert main(["--self-test"]) == 0
    assert "OK" in capsys.readouterr().out


def test_self_test_writes_report_file(tmp_path):
    from app.main import main

    report = tmp_path / "r.txt"
    assert main(["--self-test", str(report)]) == 0
    assert report.read_text(encoding="utf-8").startswith("OK")


def test_self_test_failure_is_reported_not_raised(tmp_path, monkeypatch):
    import app.main as m

    def boom(model_dir=None):
        raise ImportError("ctranslate2 missing")

    monkeypatch.setattr(m, "self_test", boom)
    report = tmp_path / "r.txt"
    assert m.main(["--self-test", str(report)]) == 1
    assert "ctranslate2 missing" in report.read_text(encoding="utf-8")


def test_retired_worker_signals_are_ignored(qtbot):
    app, factory, _, _, _ = _app(qtbot)
    old = factory.workers[0]
    app.model_actions["opus-mt-en-vi"].trigger()
    old.progress.emit(1, 2)
    old.ready.emit()
    assert not app.ready and "1/0 MB" not in app.status_action.text()
    old.failed.emit("old model broke")
    assert app.error is None and not app.retry_action.isVisible()
    factory.workers[1].ready.emit()
    assert app.ready and "opus-mt-en-vi" in app.status_action.text()


def test_quit_waits_for_threads_and_force_exits_if_stuck(qtbot, monkeypatch):
    import app.main as m

    app, factory, _, _, _ = _app(qtbot)
    exits = []
    monkeypatch.setattr(m.QApplication, "quit", staticmethod(lambda: None))
    app._exit = lambda code: exits.append(code)
    waited = []
    app._thread.wait = lambda ms=0: (waited.append(ms), False)[1]  # still loading a model
    app.quit()
    assert waited and waited[0] > 0
    assert exits == [0]


def test_new_selection_closes_previous_result(qtbot):
    app, factory, hotkeys, selector, _ = _app(qtbot)
    factory.workers[0].ready.emit()
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: bool(factory.workers[0].jobs), timeout=2000)
    factory.workers[0].job_done.emit(factory.workers[0].jobs[0].id, SEGS)
    assert app.region_overlay.isVisible()
    hotkeys.triggered.emit("translate_region")
    assert not app.region_overlay.isVisible() and selector.begun == 2


def test_fullscreen_closes_overlays_before_capturing(qtbot):
    app, factory, hotkeys, selector, captures = _app(qtbot)
    factory.workers[0].ready.emit()
    hotkeys.triggered.emit("translate_fullscreen")
    first = app.fullscreen_overlay
    seen_visible = []
    original = app._capture
    app._capture = lambda *r: (seen_visible.append(first.isVisible()), original(*r))[1]
    hotkeys.triggered.emit("translate_fullscreen")
    assert seen_visible == [False]


def test_superseded_region_job_clears_its_popup(qtbot):
    app, factory, hotkeys, selector, _ = _app(qtbot)
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: bool(factory.workers[0].jobs), timeout=2000)
    region_job = factory.workers[0].jobs[0]
    assert app.region_overlay.isVisible()  # "Đang tải model…"
    hotkeys.triggered.emit("translate_fullscreen")
    factory.workers[0].job_failed.emit(region_job.id, "superseded")
    assert app._region_job is None and not app.region_overlay.isVisible()


def _live_app(qtbot, tmp_path, current=None):
    fg = Foreground()
    fg.game = current
    if current is not None:
        fg.windows[current.exe] = current
    app, factory, hotkeys, selector, captures = _app(qtbot, tmp_path=tmp_path, fg=fg)
    app._live_timer_enabled = False
    return app, factory, hotkeys, selector, captures, fg


def _saved(tmp_path, exe="game.exe", **kw):
    from app.profiles import Profile, ProfileStore

    store = ProfileStore(tmp_path / "profiles")
    store.save(Profile(exe, "Game", **kw))
    return store


def test_toggle_live_without_regions_opens_selector_and_saves_the_game_profile(qtbot, tmp_path):
    from app.profiles import ProfileStore

    app, factory, hotkeys, selector, _, _ = _live_app(qtbot, tmp_path, game(client=(0, 0, 1000, 500)))
    hotkeys.triggered.emit("toggle_live")
    assert selector.begun == 1 and app.live is None
    selector.selected.emit((100, 400, 800, 100))
    p = ProfileStore(tmp_path / "profiles").get("game.exe")
    assert p.name == "Game" and p.regions == [(0.1, 0.8, 0.8, 0.2)]
    assert app.live.running and app.live_action.isChecked() and app.live.regions == [(100, 400, 800, 100)]
    assert [j.mode for j in factory.workers[0].all_jobs] == ["set_game"]  # the game's glossary + overrides
    hotkeys.triggered.emit("toggle_live")
    assert not app.live.running and not app.live_action.isChecked()


def test_toggle_live_with_a_saved_profile_starts_directly(qtbot, tmp_path):
    _saved(tmp_path, regions=[(0.1, 0.8, 0.8, 0.2)])
    app, _, hotkeys, selector, _, _ = _live_app(qtbot, tmp_path, game(client=(0, 0, 1000, 500)))
    hotkeys.triggered.emit("toggle_live")
    assert selector.begun == 0 and app.live.running and app.live.regions == [(100, 400, 800, 100)]


def test_add_region_and_ignore_region_from_the_tray(qtbot, tmp_path):
    from app.profiles import ProfileStore

    _saved(tmp_path, regions=[(0.1, 0.8, 0.8, 0.2)])
    app, _, hotkeys, selector, _, _ = _live_app(qtbot, tmp_path, game(client=(0, 0, 1000, 500)))
    app._remember_game()
    app.add_live_region()
    selector.selected.emit((0, 0, 500, 50))
    app.add_ignore_region()
    selector.selected.emit((950, 450, 50, 50))
    p = ProfileStore(tmp_path / "profiles").get("game.exe")
    assert p.regions == [(0.1, 0.8, 0.8, 0.2), (0.0, 0.0, 0.5, 0.1)] and p.ignore == [(0.95, 0.9, 0.05, 0.1)]
    app.clear_live_regions()
    assert ProfileStore(tmp_path / "profiles").get("game.exe").regions == []


def test_live_results_reach_the_controller_and_quit_stops_it(qtbot, tmp_path):
    from app.text.postprocess import Paragraph

    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    app, factory, hotkeys, _, _, _ = _live_app(qtbot, tmp_path, game())
    w = factory.workers[0]
    w.ready.emit()
    hotkeys.triggered.emit("toggle_live")
    app.live.ocr_job = 900
    app.live._ocr_final[900] = True
    w.ocr_done.emit(900, [[Paragraph("text", "Hello.", ["Hello."], 0, 0, 300, 40)]])
    tr = w.jobs[-1]
    assert tr.mode == "live_translate"
    seg = Segment("text", "Hello.", "Xin chào.", (0, 0, 300, 40))
    w.partial.emit(tr.id, [[seg]])
    assert [b.text for b in app.live._overlays[0].blocks.values()] == ["Xin chào."]
    w.job_done.emit(tr.id, [[seg]])
    assert app.live.translate_job is None
    app._exit = lambda code: None
    app.quit()
    assert not app.live.running


def test_screen_scope_needs_no_selection(qtbot, tmp_path):
    from app.profiles import ProfileStore

    app, _, hotkeys, selector, _, _ = _live_app(qtbot, tmp_path, game(client=(100, 100, 800, 600)))
    app._remember_game()
    app.live_scope_actions["screen"].trigger()
    assert ProfileStore(tmp_path / "profiles").get("game.exe").scope == "screen"
    hotkeys.triggered.emit("toggle_live")
    assert selector.begun == 0 and app.live.running and app.live.regions == [(0, 0, 1920, 1080)]
    assert app.live.scope == "screen"


def test_switching_to_another_game_restarts_live_with_its_profile(qtbot, tmp_path):
    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    _saved(tmp_path, exe="b.exe", regions=[(0.5, 0.5, 0.5, 0.5)])
    a = game()
    app, factory, hotkeys, _, _, fg = _live_app(qtbot, tmp_path, a)
    hotkeys.triggered.emit("toggle_live")
    old = app.live._overlays[0]
    b = game("b.exe", client=(0, 0, 1000, 1000))
    fg.game, fg.windows["b.exe"] = b, b
    app._check_foreground()
    assert app.live.running and app.live.regions == [(500, 500, 500, 500)]
    assert not old.isVisible()
    sets = [j for j in factory.workers[0].all_jobs if j.mode == "set_game"]
    assert [j.payload["game"] for j in sets] == ["game.exe", "b.exe"]
    fg.game = None  # our own window / the desktop: Live stays on b.exe
    app._check_foreground()
    assert app.live.regions == [(500, 500, 500, 500)]


def test_minimized_game_pauses_live(qtbot, tmp_path):
    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    app, factory, hotkeys, _, captures, fg = _live_app(qtbot, tmp_path, game())
    hotkeys.triggered.emit("toggle_live")
    fg.windows["game.exe"] = game(minimized=True)
    n = len(captures)
    app.live.tick(0)
    assert len(captures) == n and "thu nhỏ" in app.last_message


def test_edit_last_without_results_says_so(qtbot, tmp_path):
    app, _, hotkeys, _, _, _ = _live_app(qtbot, tmp_path, game())
    hotkeys.triggered.emit("edit_last")
    assert app.last_message == "Chưa có bản dịch nào để sửa."


def test_edit_last_saves_overrides_terms_and_tells_the_worker(qtbot, tmp_path):
    import json

    from app.gui.correct_dialog import Correction
    from app.profiles import ProfileStore

    app, factory, hotkeys, selector, _, _ = _live_app(qtbot, tmp_path, game())

    class FakeDialog:
        def __init__(self, segments):
            self.segments = segments

        def exec(self):
            return True

        def corrections(self):
            return [Correction("Hello.", "Xin chào.", "Chào cậu.")]

        def parsed_terms(self):
            return [("Arcanist", None)]

    app._dialog_factory = FakeDialog
    factory.workers[0].ready.emit()
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: bool(factory.workers[0].jobs), timeout=2000)
    job = factory.workers[0].jobs[-1]
    factory.workers[0].job_done.emit(job.id, SEGS)
    hotkeys.triggered.emit("edit_last")
    fix = factory.workers[0].all_jobs[-1]
    assert fix.mode == "correct" and fix.payload["corrections"] == [["Hello.", "Xin chào.", "Chào cậu."]]
    assert fix.payload["terms"] == [["Arcanist", None]]
    assert ProfileStore(tmp_path / "profiles").get("game.exe").overrides == {"Hello.": "Chào cậu."}
    terms = json.loads((tmp_path / "glossary" / "games" / "game.exe.json").read_text(encoding="utf-8"))
    assert terms["entries"] == [{"source": "Arcanist", "type": "keep", "case_sensitive": True}]
    assert "Chào cậu." in app.region_overlay.text()


def test_style_menu_is_saved_in_the_game_profile_and_used_by_live(qtbot, tmp_path):
    from app.profiles import ProfileStore

    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    app, _, hotkeys, _, _, _ = _live_app(qtbot, tmp_path, game())
    app._remember_game()
    assert app.live_style_actions["match"].isChecked()  # default: like the game
    app.live_style_actions["classic"].trigger()
    assert ProfileStore(tmp_path / "profiles").get("game.exe").style == "classic"
    hotkeys.triggered.emit("toggle_live")
    assert app.live.style == "classic"


def test_i3_switching_model_restarts_live_so_no_job_stays_stuck(qtbot, tmp_path):
    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    app, factory, hotkeys, _, _, _ = _live_app(qtbot, tmp_path, game())
    hotkeys.triggered.emit("toggle_live")
    app.live.ocr_job = 900
    app.switch_model("opus-mt-en-vi")
    assert app.live.running and app.live.ocr_job is None
    assert [j.mode for j in factory.workers[1].all_jobs] == ["set_game"]


def test_i4_one_shot_translation_uses_the_game_profile(qtbot, tmp_path):
    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)], overrides={"Hello.": "Chào."})
    app, factory, hotkeys, selector, _, _ = _live_app(qtbot, tmp_path, game())
    hotkeys.triggered.emit("translate_region")
    selector.selected.emit((10, 10, 200, 100))
    qtbot.waitUntil(lambda: any(j.mode == "region" for j in factory.workers[0].jobs), timeout=2000)
    modes = [j.mode for j in factory.workers[0].all_jobs]
    assert modes.index("set_game") < modes.index("region")


def test_i5_switching_to_a_game_without_regions_keeps_live_and_no_selector(qtbot, tmp_path):
    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    _saved(tmp_path, exe="b.exe")  # no regions
    app, _, hotkeys, selector, _, fg = _live_app(qtbot, tmp_path, game())
    hotkeys.triggered.emit("toggle_live")
    b = game("b.exe")
    fg.game, fg.windows["b.exe"] = b, b
    app._check_foreground()
    assert selector.begun == 0 and app.live.running and app._live_game == "game.exe"


def test_settings_window_applies_and_remembers(qtbot, tmp_path):
    import json

    from app.gui.settings_dialog import SettingsValues
    from app.profiles import ProfileStore

    _saved(tmp_path, regions=[(0.0, 0.0, 0.5, 0.5)])
    app, factory, hotkeys, _, _, _ = _live_app(qtbot, tmp_path, game())
    hotkeys.triggered.emit("toggle_live")

    class FakeSettings:
        def __init__(self, values):
            self.shown = values

        def exec(self):
            return True

        def values(self):
            return SettingsValues("classic", 1.25, "shrink", "opus-mt-en-vi", self.shown.hotkeys)

    app._settings_factory = FakeSettings
    app.open_settings()
    assert ProfileStore(tmp_path / "profiles").get("game.exe").style == "classic"
    assert (app.config.overlay.text_scale, app.config.overlay.long_text) == (1.25, "shrink")
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["model"] == "opus-mt-en-vi"
    assert len(factory.workers) == 2 and app.config.translator.model == "opus-mt-en-vi"  # model switched
    assert app.live.running and app.live.style == "classic"
