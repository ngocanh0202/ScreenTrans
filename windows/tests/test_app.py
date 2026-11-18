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

    def submit(self, job):
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


def _app(qtbot, ok=True, tmp_path=None):
    from app.main import TrayApp

    cfg = Config()
    if tmp_path is not None:
        cfg.paths.data_dir = str(tmp_path)
    factory, hotkeys, selector = WorkerFactory(), FakeHotkeys(ok), FakeSelector()
    captures = []

    def capture(x, y, w, h):
        captures.append((x, y, w, h))
        return Image.new("RGB", (max(w, 1), max(h, 1)))

    app = TrayApp(cfg, worker_factory=factory, hotkeys=hotkeys, selector=selector, capture=capture,
                  monitor_at=lambda x, y: (0, 0, 1920, 1080), cursor=lambda: (500, 500), capture_delay_ms=0)
    app.start()
    return app, factory, hotkeys, selector, captures


SEGS = [Segment("name", "Druvis III", None, (0, 0, 10, 10)),
        Segment("text", "Hello.", "Xin chào.", (0, 20, 100, 40))]


def test_registers_both_hotkeys(qtbot):
    _, _, hotkeys, _, _ = _app(qtbot)
    assert [n for n, _ in hotkeys.registered] == ["translate_region", "translate_fullscreen", "toggle_live"]


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


def _live_app(qtbot, tmp_path):
    app, factory, hotkeys, selector, captures = _app(qtbot, tmp_path=tmp_path)
    app._live_timer_enabled = False
    return app, factory, hotkeys, selector, captures


def test_toggle_live_without_regions_opens_selector_then_starts(qtbot, tmp_path):
    from app.live.regions import load_live_regions

    app, factory, hotkeys, selector, _ = _live_app(qtbot, tmp_path)
    hotkeys.triggered.emit("toggle_live")
    assert selector.begun == 1 and app.live is None
    selector.selected.emit((10, 10, 300, 80))
    assert load_live_regions(tmp_path) == [(10, 10, 300, 80)]
    assert app.live is not None and app.live.running and app.live_action.isChecked()
    assert factory.workers[0].jobs == []  # a live selection is not a one-shot translation
    hotkeys.triggered.emit("toggle_live")
    assert not app.live.running and not app.live_action.isChecked()


def test_toggle_live_with_saved_region_starts_directly(qtbot, tmp_path):
    from app.live.regions import save_live_regions

    save_live_regions(tmp_path, [(10, 10, 300, 80)])
    app, _, hotkeys, selector, _ = _live_app(qtbot, tmp_path)
    hotkeys.triggered.emit("toggle_live")
    assert selector.begun == 0 and app.live.running and app.live.regions == [(10, 10, 300, 80)]


def test_live_results_reach_the_controller_and_quit_stops_it(qtbot, tmp_path):
    from app.live.regions import save_live_regions
    from app.text.postprocess import Paragraph

    save_live_regions(tmp_path, [(10, 10, 300, 80)])
    app, factory, hotkeys, _, _ = _live_app(qtbot, tmp_path)
    w = factory.workers[0]
    w.ready.emit()
    hotkeys.triggered.emit("toggle_live")
    app.live.ocr_job = 900
    app.live._ocr_final[900] = True
    w.ocr_done.emit(900, [[Paragraph("text", "Hello.", ["Hello."], 0, 0, 300, 40)]])
    tr = w.jobs[-1]
    assert tr.mode == "live_translate"
    seg = Segment("text", "Hello.", "Xin chào.", (0, 0, 50, 10))
    w.partial.emit(tr.id, [[seg]])
    assert [b.text for b in app.live._overlays[0].blocks.values()] == ["Xin chào."]
    w.job_done.emit(tr.id, [[seg]])
    assert app.live.translate_job is None
    app._exit = lambda code: None
    app.quit()
    assert not app.live.running


def test_live_scope_menu_persists_and_screen_needs_no_selection(qtbot, tmp_path):
    from app.live.regions import load_live_scope

    app, _, hotkeys, selector, _ = _live_app(qtbot, tmp_path)
    app.live_scope_actions["screen"].trigger()
    assert load_live_scope(tmp_path) == "screen" and app.live_scope == "screen"
    hotkeys.triggered.emit("toggle_live")
    assert selector.begun == 0 and app.live.running and app.live.regions == [(0, 0, 1920, 1080)]
    assert app.live.scope == "screen"
