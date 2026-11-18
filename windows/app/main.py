"""ScreenTrans tray app: Ctrl+Alt+T translates a dragged region, Ctrl+Alt+F the whole screen,
Ctrl+Alt+L toggles Live (translate automatically whenever the text in the Live region changes)."""
import argparse
import copy
import itertools
import os
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRect, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app import factory
from app.capture import capture_region
from app.config import Config, load_config
from app.glossary import COMMON_GLOSSARY, Glossary, games_dir
from app.gui.fullscreen import FullscreenOverlay
from app.gui.hotkeys import HotkeyManager
from app.gui.live_overlay import AreaOverlay
from app.gui.overlay import ResultOverlay, physical_to_logical
from app.gui.selector import RegionSelector
from app.gui.win32 import cursor_pos_physical, monitor_rect_at
from app.gui.worker import SUPERSEDED, Job, start_worker
from app.live.controller import LiveController
from app.live.machine import LiveParams
from app.live.regions import load_live_regions, load_live_scope, save_live_regions, save_live_scope
from app.paths import default_config_path

MODELS = ["vinai-en2vi", "opus-mt-en-vi"]
HOTKEYS = [("translate_region", "translate_region"), ("translate_fullscreen", "translate_fullscreen"),
           ("toggle_live", "toggle_live")]
LIVE_SCOPES = [("screen", "Toàn màn hình"), ("region", "Vùng")]
TRANSLATING_DELAY_MS = 300
CAPTURE_DELAY_MS = 80  # let the selector shade disappear from the screen before capturing
QUIT_WAIT_MS = 3000
LOADING = "Đang tải model…"
TRANSLATING = "Đang dịch…"


def display_combo(combo: str) -> str:
    return "+".join(p.strip().capitalize() for p in combo.split("+"))


def app_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(37, 99, 235))
    p.setPen(QColor(37, 99, 235))
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor(255, 255, 255))
    p.setFont(QFont("Segoe UI", 30, QFont.Bold))
    p.drawText(pix.rect(), 0x84, "T")  # Qt.AlignCenter
    p.end()
    return QIcon(pix)


def screen_for_physical(x: int, y: int):
    """QScreen whose physical area contains (x, y); Qt keeps each screen's native origin."""
    for screen in QGuiApplication.screens():
        g, dpr = screen.geometry(), screen.devicePixelRatio()
        if g.left() <= x < g.left() + g.width() * dpr and g.top() <= y < g.top() + g.height() * dpr:
            return screen
    return QGuiApplication.primaryScreen()


def game_glossaries() -> list[Path]:
    return sorted(games_dir().glob("*.json"))


class TrayApp(QObject):
    def __init__(
        self,
        config: Config,
        worker_factory=start_worker,
        hotkeys=None,
        selector=None,
        capture: Callable[[int, int, int, int], object] = capture_region,
        monitor_at: Callable[[int, int], tuple[int, int, int, int]] = monitor_rect_at,
        cursor: Callable[[], tuple[int, int]] = cursor_pos_physical,
        capture_delay_ms: int = CAPTURE_DELAY_MS,
    ):
        super().__init__()
        self.config = config
        self._worker_factory = worker_factory
        self.hotkeys = hotkeys if hotkeys is not None else HotkeyManager()
        self.selector = selector if selector is not None else RegionSelector()
        self._capture = capture
        self._monitor_at = monitor_at
        self._cursor = cursor
        self._capture_delay_ms = capture_delay_ms
        self._exit = os._exit  # last resort when a worker thread is stuck in a download / model load
        self._ids = itertools.count(1)
        self._thread = None
        self.worker = None
        self._retired = []
        self.ready = False
        self.error: str | None = None
        self.last_message = ""
        self.region_overlay: ResultOverlay | None = None
        self.fullscreen_overlay: FullscreenOverlay | None = None
        self._region_job: int | None = None
        self._region_rect: tuple[int, int, int, int] | None = None
        self._fullscreen_job: int | None = None
        self._fullscreen_origin = (0, 0)
        self.live: LiveController | None = None
        self.live_scope = load_live_scope(self._data_dir())
        self._live_timer_enabled = True
        self._selecting_live = False
        self._build_tray()
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.selector.selected.connect(self._on_region_selected)

    # ---- tray -------------------------------------------------------------------------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon())
        self.tray.setToolTip("ScreenTrans")
        menu = QMenu()
        hk = self.config.hotkeys
        menu.addAction(f"Dịch vùng ({display_combo(hk.translate_region)})", self.translate_region)
        menu.addAction(f"Toàn màn hình ({display_combo(hk.translate_fullscreen)})", self.translate_fullscreen)
        self.live_action = menu.addAction(f"Live ({display_combo(hk.toggle_live)})", self.toggle_live)
        self.live_action.setCheckable(True)
        scopes = menu.addMenu("Live dịch")
        scope_group = QActionGroup(menu)
        self.live_scope_actions: dict[str, QAction] = {}
        for scope, label in LIVE_SCOPES:
            action = scopes.addAction(label)
            action.setCheckable(True)
            action.setChecked(scope == self.live_scope)
            action.triggered.connect(lambda checked=False, sc=scope: self.set_live_scope(sc))
            scope_group.addAction(action)
            self.live_scope_actions[scope] = action
        menu.addAction("Chọn lại vùng Live", self.select_live_region)
        menu.addSeparator()
        self.status_action = menu.addAction(LOADING)
        self.status_action.setEnabled(False)
        self.retry_action = menu.addAction("Thử lại", self.restart_worker)
        self.retry_action.setVisible(False)
        models = menu.addMenu("Model")
        group = QActionGroup(menu)
        self.model_actions: dict[str, QAction] = {}
        for model_id in MODELS:
            action = models.addAction(model_id)
            action.setCheckable(True)
            action.setChecked(model_id == self.config.translator.model)
            action.triggered.connect(lambda checked=False, m=model_id: self.switch_model(m))
            group.addAction(action)
            self.model_actions[model_id] = action
        menu.addAction("Mở thư mục dữ liệu", self._open_data_dir)
        menu.addSeparator()
        menu.addAction("Thoát", self.quit)
        self._menu = menu
        self.tray.setContextMenu(menu)

    def notify(self, message: str) -> None:
        self.last_message = message
        self.tray.showMessage("ScreenTrans", message)

    def _data_dir(self) -> Path:
        return Path(self.config.paths.data_dir)

    def _open_data_dir(self) -> None:
        path = self._data_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ---- lifecycle ----------------------------------------------------------------------------
    def start(self) -> None:
        self.tray.show()
        failed = []
        for name, attr in HOTKEYS:
            combo = getattr(self.config.hotkeys, attr)
            try:
                ok = self.hotkeys.register(name, combo)
            except ValueError:
                ok = False
            if not ok:
                failed.append(display_combo(combo))
        if failed:
            self.notify("Không đăng ký được " + ", ".join(failed) + " (phím đang bị app khác dùng?)")
        self.restart_worker()

    def restart_worker(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            # keep the old worker alive until its thread ends; its signals are ignored (see _current)
            self._retired.append((self._thread, self.worker))
        self.ready, self.error = False, None
        self.status_action.setText(LOADING)
        self.retry_action.setVisible(False)
        cfg = copy.deepcopy(self.config)
        glossaries = game_glossaries()

        def pipeline_factory(progress):
            return factory.build_pipeline(cfg, None, glossaries, progress)

        self._thread, self.worker = self._worker_factory(pipeline_factory, connect=self._connect)

    def _connect(self, worker) -> None:
        # Connected before the worker thread starts, to bound methods of this UI-thread object.
        worker.ready.connect(self._on_ready)
        worker.failed.connect(self._on_failed)
        worker.progress.connect(self._on_progress)
        worker.segment.connect(self._on_segment)
        worker.job_done.connect(self._on_job_done)
        worker.job_failed.connect(self._on_job_failed)
        worker.ocr_done.connect(self._on_live_ocr_done)
        worker.partial.connect(self._on_live_partial)

    def switch_model(self, model_id: str) -> None:
        if model_id == self.config.translator.model and self.error is None:
            return
        self.config.translator.model = model_id
        self.restart_worker()

    def _current(self) -> bool:
        """Only the active worker may change app state; a retired one (model switch) is ignored."""
        return self.sender() is self.worker

    def quit(self) -> None:
        self.stop_live()
        closer = getattr(self.hotkeys, "close", None)
        if callable(closer):
            closer()
        self.tray.hide()
        threads = [t for t in [self._thread, *(t for t, _ in self._retired)] if t is not None]
        for t in threads:
            t.quit()
        # Destroying a running QThread aborts the process: wait, and if a thread is stuck in a
        # download or model load, end the process directly instead of crashing on exit.
        stuck = [t for t in threads if not t.wait(QUIT_WAIT_MS)]
        if stuck:
            self._exit(0)
            return
        QApplication.quit()

    # ---- worker signals -----------------------------------------------------------------------
    @Slot()
    def _on_ready(self) -> None:
        if not self._current():
            return
        self.ready = True
        self.status_action.setText(f"Sẵn sàng: {self.config.translator.model}")
        if self._region_job is not None and self.region_overlay is not None and self.region_overlay.isVisible():
            self.region_overlay.show_loading(TRANSLATING)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        if not self._current():
            return
        self.error = message
        self.status_action.setText(f"Lỗi: {message[:80]}")
        self.retry_action.setVisible(True)
        self.notify(message)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        if not self._current():
            return
        self.status_action.setText(f"{LOADING} {done / 1e6:.0f}/{total / 1e6:.0f} MB")

    @Slot(int, object)
    def _on_segment(self, job_id: int, segment) -> None:
        if not self._current():
            return
        if job_id == self._fullscreen_job and self.fullscreen_overlay is not None:
            self.fullscreen_overlay.add_segment(segment, self._fullscreen_origin)

    @Slot(int, object)
    def _on_live_ocr_done(self, job_id: int, per_region) -> None:
        if self._current() and self.live is not None:
            self.live.on_ocr_done(job_id, per_region)

    @Slot(int, object)
    def _on_live_partial(self, job_id: int, per_region) -> None:
        if self._current() and self.live is not None:
            self.live.on_partial(job_id, per_region)

    @Slot(int, object)
    def _on_job_done(self, job_id: int, segments) -> None:
        if not self._current():
            return
        if self.live is not None and self.live.owns(job_id):
            self.live.on_job_done(job_id, segments)
            return
        if job_id == self._region_job:
            self._region_job = None
            self.region_overlay.show_segments(segments, self.config.overlay.show_source)
            self._present_region()
        elif job_id == self._fullscreen_job and self.fullscreen_overlay is not None:
            self._fullscreen_job = None
            self.fullscreen_overlay.finish()

    @Slot(int, str)
    def _on_job_failed(self, job_id: int, why: str) -> None:
        if not self._current():
            return
        if self.live is not None and self.live.owns(job_id):
            self.live.on_job_failed(job_id, why)
            return
        if why == SUPERSEDED:  # a newer job replaced it: drop its pending indicator
            if job_id == self._region_job:
                self._region_job = None
                if self.region_overlay is not None:
                    self.region_overlay.close()
            elif job_id == self._fullscreen_job and self.fullscreen_overlay is not None:
                self._fullscreen_job = None
                self.fullscreen_overlay.close()
            return
        if job_id == self._region_job:
            self._region_job = None
            self.region_overlay.show_error(why)
            self._present_region()
        elif job_id == self._fullscreen_job and self.fullscreen_overlay is not None:
            self._fullscreen_job = None
            self.fullscreen_overlay.finish()
            self.notify(why)

    # ---- hotkeys --------------------------------------------------------------------------------
    @Slot(str)
    def _on_hotkey(self, name: str) -> None:
        if name == "translate_region":
            self.translate_region()
        elif name == "translate_fullscreen":
            self.translate_fullscreen()
        elif name == "toggle_live":
            self.toggle_live()

    def _close_overlays(self) -> None:
        """Results from the previous press must not grab input or end up in the next capture."""
        if self.region_overlay is not None:
            self.region_overlay.close()
        if self.fullscreen_overlay is not None:
            self.fullscreen_overlay.close()

    def translate_region(self) -> None:
        self._close_overlays()
        self._selecting_live = False
        self.selector.begin()

    @Slot(tuple)
    def _on_region_selected(self, rect) -> None:
        if self._selecting_live:
            self._selecting_live = False
            save_live_regions(self._data_dir(), [tuple(rect)])
            self.start_live()
            return
        QTimer.singleShot(self._capture_delay_ms, lambda r=tuple(rect): self._run_region(r))

    def _run_region(self, rect: tuple[int, int, int, int]) -> None:
        image = self._capture(*rect)
        job = Job(next(self._ids), "region", image, (rect[0], rect[1]))
        self._region_job, self._region_rect = job.id, rect
        if self.region_overlay is None:
            self.region_overlay = ResultOverlay(self.config.overlay)
        if self.error is not None:
            self.region_overlay.show_error(self.error)
            self._present_region()
        elif not self.ready:
            self.region_overlay.show_loading(LOADING)
            self._present_region()
        else:
            QTimer.singleShot(TRANSLATING_DELAY_MS, lambda jid=job.id: self._show_translating(jid))
        self.worker.submit(job)

    def _show_translating(self, job_id: int) -> None:
        if self._region_job == job_id:
            self.region_overlay.show_loading(TRANSLATING)
            self._present_region()

    def _present_region(self) -> None:
        x, y, w, h = self._region_rect
        screen = screen_for_physical(x + w // 2, y + h // 2)
        region = physical_to_logical(self._region_rect, screen.geometry(), screen.devicePixelRatio())
        self.region_overlay.present(region, screen.geometry())

    def translate_fullscreen(self) -> None:
        self._close_overlays()
        mon = self._monitor_at(*self._cursor())
        image = self._capture(*mon)
        screen = screen_for_physical(mon[0] + mon[2] // 2, mon[1] + mon[3] // 2)
        self.fullscreen_overlay = FullscreenOverlay(self.config.overlay, QRect(screen.geometry()),
                                                    screen.devicePixelRatio())
        self.fullscreen_overlay.present()
        job = Job(next(self._ids), "fullscreen", image, (mon[0], mon[1]))
        self._fullscreen_job, self._fullscreen_origin = job.id, job.origin
        if self.error is not None:
            self.fullscreen_overlay.finish()
            self.notify(self.error)
            return
        self.worker.submit(job)


    # ---- live -------------------------------------------------------------------------------------
    def toggle_live(self) -> None:
        if self.live is not None and self.live.running:
            self.stop_live()
        elif self.live_scope == "screen" or load_live_regions(self._data_dir()):
            self.start_live()
        else:
            self.select_live_region()

    def select_live_region(self) -> None:
        self.stop_live()
        self._close_overlays()
        self._selecting_live = True
        self.selector.begin()

    def set_live_scope(self, scope: str) -> None:
        self.live_scope = scope
        save_live_scope(self._data_dir(), scope)
        if self.live is not None and self.live.running:
            self.start_live()  # restart with the new scope

    def start_live(self) -> None:
        if self.live_scope == "screen":
            regions = [tuple(self._monitor_at(*self._cursor()))]  # the monitor under the mouse
        else:
            regions = load_live_regions(self._data_dir())
        if not regions:
            self.select_live_region()
            return
        self.stop_live()
        lc = self.config.live
        params = LiveParams(lc.interval_ms, lc.active_interval_ms, lc.settle_ms, lc.max_wait_ms, lc.change_threshold,
                            lc.partial_interval_ms)
        self.live = LiveController(
            params, capture=self._capture, submit=lambda job: self.worker.submit(job),
            next_id=lambda: next(self._ids), notify=self.notify, overlay_factory=self._live_overlay,
            scope=self.live_scope, area_min_interval_ms=lc.area_min_interval_ms,
            area_max_blocks=lc.area_max_blocks, use_timer=self._live_timer_enabled)
        self.live.start(regions)
        self.live_action.setChecked(True)

    def stop_live(self) -> None:
        if self.live is not None:
            self.live.stop()
        self.live_action.setChecked(False)

    def _live_overlay(self, region: tuple[int, int, int, int]):
        x, y, w, h = region
        screen = screen_for_physical(x + w // 2, y + h // 2)
        return AreaOverlay(self.config.overlay, QRect(screen.geometry()), screen.devicePixelRatio())


def self_test(model_dir: Path | None = None) -> int:
    """Packaging check: every heavy runtime import must resolve inside the frozen app; with a model
    directory, also load it and translate one sentence (AutoTokenizer imports modules lazily)."""
    import ctranslate2  # noqa: F401
    import mss  # noqa: F401
    from transformers import MarianTokenizer, MBartTokenizerFast  # noqa: F401

    from app.ocr.windows_ocr import language_available

    Glossary.load(*game_glossaries(), COMMON_GLOSSARY)
    app_icon()
    sample = ""
    if model_dir is not None:
        from app.translate.ct2 import Ct2Translator

        sample = ", sample: " + Ct2Translator(model_dir).translate(["Good morning."])[0]
    print(f"OK (ctranslate2 {ctranslate2.__version__}, english ocr: {language_available('en')}{sample})")
    return 0


def _run_self_test(report: str, model_dir: Path | None = None) -> int:
    """The packaged app has no console and shows a dialog on uncaught errors: never let one escape."""
    import io
    import traceback
    from contextlib import redirect_stdout

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = self_test(model_dir)
    except Exception:
        buf.write("FAIL\n" + traceback.format_exc())
        code = 1
    if report == "-":
        if sys.stdout is not None:
            sys.stdout.write(buf.getvalue())
    else:
        Path(report).write_text(buf.getvalue(), encoding="utf-8")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ScreenTrans")
    ap.add_argument("--config", type=Path, default=default_config_path())
    ap.add_argument("--self-test", nargs="?", const="-", metavar="REPORT",
                    help="load resources and exit (CI check); write the result to REPORT (default stdout)")
    ap.add_argument("--model-dir", type=Path, help="with --self-test: also load this model and translate")
    args = ap.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    config = load_config(args.config)
    if args.self_test:
        return _run_self_test(args.self_test, args.model_dir)
    tray = TrayApp(config)
    tray.start()
    return app.exec()
