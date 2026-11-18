"""Windows Live: watch regions, OCR when the text settles, translate progressively into overlays.

The controller lives on the UI thread; OCR and translation run as worker jobs ("live_ocr",
"live_translate"). Rules for when to OCR / translate come from LiveMachine (shared fixtures).
"""
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from app.live.blocks import BlockTracker, RateLimiter
from app.live.machine import Action, LiveMachine, LiveParams
from app.live.thumb import diff, gray_thumb

Region = tuple[int, int, int, int]  # x, y, w, h in physical pixels


class LiveController(QObject):
    def __init__(
        self,
        params: LiveParams,
        capture: Callable[[int, int, int, int], object],
        submit: Callable[[object], None],
        next_id: Callable[[], int],
        notify: Callable[[str], None],
        overlay_factory: Callable[[Region], object],
        area: bool = False,
        area_min_interval_ms: int = 1000,
        area_max_blocks: int = 30,
        clock: Callable[[], int] = lambda: int(time.monotonic() * 1000),
        use_timer: bool = True,
    ):
        super().__init__()
        self.params = params
        self._capture = capture
        self._submit = submit
        self._next_id = next_id
        self._notify = notify
        self._overlay_factory = overlay_factory
        self.area = area
        self._area_min_interval_ms = area_min_interval_ms
        self._area_max_blocks = area_max_blocks
        self._clock = clock
        self._use_timer = use_timer
        self.running = False
        self.regions: list[Region] = []
        self.machine = LiveMachine(params)
        self.ocr_job: int | None = None
        self.translate_job: int | None = None
        self._overlays: list = []
        self._prev: list = []
        self._reported_offscreen = False
        self._tracker = BlockTracker(area_max_blocks)
        self._limiter = RateLimiter(area_min_interval_ms)
        self._pending_ocr = False
        self._pending_keys: list[str] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.tick(self._clock()))

    # ---- lifecycle ----------------------------------------------------------------------------
    def start(self, regions: list[Region]) -> None:
        self.stop()
        self.regions = list(regions)
        self.machine = LiveMachine(self.params)
        self._tracker = BlockTracker(self._area_max_blocks)
        self._limiter = RateLimiter(self._area_min_interval_ms)
        self._prev = [None] * len(self.regions)
        self._overlays = [self._overlay_factory(r) for r in self.regions]
        self._reported_offscreen = False
        self.running = True
        self._schedule(0)

    def stop(self) -> None:
        self.running = False
        self._timer.stop()
        for o in self._overlays:
            o.close()
        self._overlays = []
        self.ocr_job = self.translate_job = None
        self._pending_ocr = False
        self._pending_keys = []

    def _schedule(self, delay_ms: int) -> None:
        if self._use_timer and self.running:
            self._timer.start(delay_ms)

    # ---- frames ---------------------------------------------------------------------------------
    def tick(self, now_ms: int) -> None:
        if not self.running:
            return
        images = []
        worst = 0.0
        for i, (x, y, w, h) in enumerate(self.regions):
            try:
                img = self._capture(x, y, w, h)
            except Exception:  # monitor unplugged / region off screen: skip it, report once
                if not self._reported_offscreen:
                    self._reported_offscreen = True
                    self._notify("Vùng Live nằm ngoài màn hình — chọn lại vùng Live.")
                images.append(None)
                continue
            images.append(img)
            thumb = gray_thumb(img)
            prev = self._prev[i]
            if prev is not None:
                worst = max(worst, diff(prev, thumb))
            self._prev[i] = thumb
        action = self.machine.on_frame(now_ms, worst)
        if action is Action.OCR:
            self._pending_ocr = True
        if self._pending_ocr and any(img is not None for img in images):
            if not self.area or self._limiter.allow(now_ms):
                self._pending_ocr = False
                self.ocr_job = self._next_id()
                from app.gui.worker import Job

                self._submit(Job(self.ocr_job, "live_ocr", None, (0, 0),
                                 images=[img for img in images if img is not None]))
        self._schedule(self.machine.next_delay_ms())

    # ---- worker results -------------------------------------------------------------------------
    def on_ocr_done(self, job_id: int, paragraphs_per_region: list) -> None:
        if not self.running or job_id != self.ocr_job:
            return
        self.ocr_job = None
        from app.gui.worker import Job

        if self.area:
            d = self._tracker.update(paragraphs_per_region[0] if paragraphs_per_region else [])
            for b in d.removed:
                remove = getattr(self._overlays[0], "remove_block", None)
                if remove:
                    remove(b.key)
            if d.added:
                self._pending_keys = [b.key for b in d.added]
                self.translate_job = self._next_id()
                self._submit(Job(self.translate_job, "live_translate", None, (0, 0),
                                 paragraphs=[[b.paragraph for b in d.added]]))
            return
        text = " ".join(p.text for ps in paragraphs_per_region for p in ps)
        if self.machine.on_text(self._clock(), text) == "translate":
            self.translate_job = self._next_id()
            self._submit(Job(self.translate_job, "live_translate", None, (0, 0), paragraphs=paragraphs_per_region))

    def on_partial(self, job_id: int, segments_per_region: list) -> None:
        if not self.running or job_id != self.translate_job:
            return
        if self.area:
            x, y, _, _ = self.regions[0]
            set_block = getattr(self._overlays[0], "set_block", None)
            if set_block:
                for key, seg in zip(self._pending_keys, segments_per_region[0] if segments_per_region else []):
                    set_block(key, seg, (x, y))
            return
        for overlay, segments in zip(self._overlays, segments_per_region):
            overlay.show_segments(segments)

    def on_job_done(self, job_id: int, segments_per_region) -> None:
        if job_id == self.translate_job:
            self.on_partial(job_id, segments_per_region)
            self.translate_job = None

    def on_job_failed(self, job_id: int, why: str) -> None:
        if job_id == self.ocr_job:
            self.ocr_job = None
        if job_id == self.translate_job:
            self.translate_job = None
