"""Windows Live (4b): watch the screen or regions, translations drawn over each text block, sentence by
sentence while the text is still typing (spec §5.6c).

The controller lives on the UI thread; OCR and translation run as worker jobs ("live_ocr",
"live_translate"). When to OCR: LiveMachine (shared/fixtures/live); which blocks are new / growing:
BlockTracker (live_blocks); which sentences are finished: SentenceGate (live_sentences).
"""
import time
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from app.live.blocks import BlockTracker, RateLimiter
from app.live.machine import Action, LiveMachine, LiveParams
from app.live.mask import ignore_mask
from app.live.sentences import SentenceGate
from app.live.style import BlockStyle, font_px_for, sample_style
from app.live.thumb import diff, gray_thumb
from app.profiles import Rel, to_px
from app.text.postprocess import Paragraph

Region = tuple[int, int, int, int]  # x, y, w, h in physical pixels


@dataclass
class _BlockState:
    kind: str = "text"
    box: tuple[float, float, float, float] = (0, 0, 0, 0)
    sentences: list[str] = field(default_factory=list)   # sentences at the last OCR (SentenceGate "previous")
    done: int = 0                                         # leading sentences that are finished
    shown: dict[int, tuple[str, str]] = field(default_factory=dict)  # index -> (source, translation)
    drawn: str = ""
    font_px: float | None = None        # the source text's size (always used)
    colors: BlockStyle | None = None    # sampled colours ("match" style), None = white on dark
    sampled: bool = False


class LiveController(QObject):
    def __init__(
        self,
        params: LiveParams,
        capture: Callable[[int, int, int, int], object],
        submit: Callable[[object], None],
        next_id: Callable[[], int],
        notify: Callable[[str], None],
        overlay_factory: Callable[[Region], object],
        scope: str = "region",
        area_min_interval_ms: int = 1000,
        area_max_blocks: int = 30,
        clock: Callable[[], int] = lambda: int(time.monotonic() * 1000),
        use_timer: bool = True,
        on_screen: Callable[[Region], bool] = lambda r: True,
        style: str = "match",
    ):
        super().__init__()
        self.params = params
        self._capture = capture
        self._submit = submit
        self._next_id = next_id
        self._notify = notify
        self._overlay_factory = overlay_factory
        self.scope = scope
        self._area_min_interval_ms = area_min_interval_ms
        self._area_max_blocks = area_max_blocks
        self._clock = clock
        self._use_timer = use_timer
        self._on_screen = on_screen
        self.style = style
        self._ocr_images: dict[int, list] = {}  # OCR job -> region images, to sample the source colours
        self._rel: list[Rel] | None = None          # regions relative to the game window (4b)
        self._ignore_rel: list[Rel] = []
        self._frame_provider: Callable[[], tuple[int, int, int, int] | None] | None = None
        self._masks: list = []
        self._reported_paused = False
        self.running = False
        self.regions: list[Region] = []
        self.machine = LiveMachine(params)
        self.ocr_job: int | None = None
        self._ocr_final: dict[int, bool] = {}
        self._requests: dict[int, list[tuple[int, str, int, str]]] = {}  # translate job -> (region, key, idx, src)
        self._inflight: set[tuple[int, str, int, str]] = set()
        self._overlays: list = []
        self._trackers: list[BlockTracker] = []
        self._blocks: dict[tuple[int, str], _BlockState] = {}
        self._prev: list = []
        self._reported_offscreen = False
        self._limiter = RateLimiter(area_min_interval_ms)
        self._pending: bool | None = None  # an OCR to submit; True = final (text stood still)
        self.last_segments: list = []      # what is shown now, for "edit last translation"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.tick(self._clock()))

    # ---- lifecycle ----------------------------------------------------------------------------
    def start(self, regions: list[Region]) -> None:
        self.stop()
        self.regions = list(regions)
        self.machine = LiveMachine(self.params)
        self._trackers = [BlockTracker(self._area_max_blocks) for _ in self.regions]
        self._limiter = RateLimiter(self._area_min_interval_ms)
        self._prev = [None] * len(self.regions)
        self._masks = [None] * len(self.regions)
        self._ignore_px: list = []
        self._rel, self._frame_provider = None, None
        self._overlays = [self._overlay_factory(r) for r in self.regions]
        self._reported_offscreen = False
        self.running = True
        self._pending = True  # translate what is already on screen
        self._schedule(0)

    def start_relative(self, rel: list[Rel], frame_provider: Callable[[], tuple[int, int, int, int] | None],
                       ignore: list[Rel] | None = None) -> None:
        """Regions relative (0-1) to a frame that may move: the game window's client area (or its monitor)."""
        frame = frame_provider()
        self.start([to_px(r, frame) if frame else (0, 0, 1, 1) for r in rel])
        self._rel, self._frame_provider, self._ignore_rel = list(rel), frame_provider, list(ignore or [])
        self._ignore_px = [to_px(r, frame) for r in self._ignore_rel] if frame else []
        self._reported_paused = False
        if frame is None:
            self.regions = []  # recomputed by the first tick that finds the window

    def _follow_window(self) -> bool:
        """Recompute regions from the game window; False while it is minimized / gone."""
        frame = self._frame_provider()
        if frame is None or frame[2] <= 0 or frame[3] <= 0:
            if not self._reported_paused:
                self._reported_paused = True
                self._notify("Game đã thu nhỏ hoặc đóng — Live tạm dừng.")
            return False
        self._reported_paused = False
        regions = [to_px(r, frame) for r in self._rel]
        if regions != self.regions:  # the window moved / resized: start over at the new place
            for (i, key) in list(self._blocks):
                if i < len(self._overlays):
                    self._overlays[i].remove_block(key)
            self._blocks.clear()
            self._trackers = [BlockTracker(self._area_max_blocks) for _ in regions]
            self._prev = [None] * len(regions)
            self._masks = [None] * len(regions)
            self._ignore_px = [to_px(r, frame) for r in self._ignore_rel]
            self.regions = regions
            self._pending = True
        return True

    def stop(self) -> None:
        self.running = False
        self._timer.stop()
        for o in self._overlays:
            o.close()
        self._overlays = []
        self.ocr_job = None
        self._ocr_final.clear()
        self._ocr_images.clear()
        self._requests.clear()
        self._inflight.clear()
        self._blocks.clear()
        self._pending = None
        self.last_segments = []

    def owns(self, job_id: int) -> bool:
        return job_id == self.ocr_job or job_id in self._ocr_final or job_id in self._requests

    @property
    def translate_job(self) -> int | None:
        """Newest translation job still running (None when idle)."""
        return max(self._requests) if self._requests else None

    def _schedule(self, delay_ms: int) -> None:
        if self._use_timer and self.running:
            self._timer.start(delay_ms)

    # ---- frames ---------------------------------------------------------------------------------
    def tick(self, now_ms: int) -> None:
        if not self.running:
            return
        if self._frame_provider is not None and not self._follow_window():
            self._schedule(self.params.interval_ms)
            return
        images = []
        worst = 0.0
        for i, (x, y, w, h) in enumerate(self.regions):
            if not self._on_screen((x, y, w, h)):
                if not self._reported_offscreen:
                    self._reported_offscreen = True
                    self._notify("Vùng Live nằm ngoài màn hình — chọn lại vùng Live.")
                images.append(None)
                continue
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
            mask = None
            if self._ignore_rel:
                if self._masks[i] is None or self._masks[i].shape != thumb.shape:
                    self._masks[i] = ignore_mask((x, y, w, h), self._ignore_px, thumb.shape[1], thumb.shape[0])
                mask = self._masks[i]
            if self._prev[i] is not None:
                worst = max(worst, diff(self._prev[i], thumb, mask))
            self._prev[i] = thumb
        action = self.machine.on_frame(now_ms, worst)
        if action is Action.OCR:
            self._pending = self.machine.final or bool(self._pending)
        elif action is Action.PARTIAL and self.ocr_job is None and self._pending is None:
            self._pending = False
        if self._pending is not None and any(img is not None for img in images):
            if self.scope != "screen" or self._limiter.allow(now_ms):
                from app.gui.worker import Job

                job_id = self._next_id()
                self._ocr_final[job_id] = self._pending
                self._ocr_images[job_id] = images
                self.ocr_job, self._pending = job_id, None
                self._submit(Job(job_id, "live_ocr", None, (0, 0), images=images))  # None keeps region slots
        self._schedule(self.machine.next_delay_ms())

    # ---- worker results -------------------------------------------------------------------------
    def on_ocr_done(self, job_id: int, paragraphs_per_region: list) -> None:
        final = self._ocr_final.pop(job_id, None)
        images = self._ocr_images.pop(job_id, None) or []
        if not self.running or final is None:
            return
        if job_id == self.ocr_job:
            self.ocr_job = None
        request: list[tuple[int, str, int, str]] = []
        for i, paragraphs in enumerate(paragraphs_per_region[: len(self.regions)]):
            if paragraphs is None:
                continue
            d = self._trackers[i].update(paragraphs)
            for b in d.removed:
                self._blocks.pop((i, b.key), None)
                self._overlays[i].remove_block(b.key)
            for b in d.added + d.grown + d.kept:
                self._style_block(i, b.key, b.paragraph, images[i] if i < len(images) else None)
                request += self._update_block(i, b.key, b.paragraph, final)
        if request:
            from app.gui.worker import Job

            tr_id = self._next_id()
            self._requests[tr_id] = request
            self._inflight.update(request)
            groups: list[list[Paragraph]] = [[] for _ in self.regions]
            for i, key, _, src in request:
                st = self._blocks[(i, key)]
                groups[i].append(Paragraph("text", src, [src], *st.box))
            self._submit(Job(tr_id, "live_translate", None, (0, 0), paragraphs=groups))

    def _style_block(self, i: int, key: str, p: Paragraph, image) -> None:
        """Font size from the source line height; colours sampled once from the block's pixels."""
        st = self._blocks.setdefault((i, key), _BlockState())
        size = font_px_for(getattr(p, "line_height", 0.0))
        if size is not None:
            st.font_px = size
        if self.style == "match" and not st.sampled and image is not None:
            st.sampled = True
            crop = image.crop((int(p.left), int(p.top), int(p.right), int(p.bottom))).convert("RGB")
            import numpy as np

            st.colors = sample_style(np.asarray(crop))

    def _update_block(self, i: int, key: str, p: Paragraph, final: bool) -> list:
        st = self._blocks.setdefault((i, key), _BlockState())
        st.kind, st.box = p.kind, (p.left, p.top, p.right, p.bottom)
        if p.kind == "name":
            st.sentences, st.done = [p.text], 1
            self._draw(i, key)
            return []
        st.done = SentenceGate.done(p.sentences, st.sentences or None, final)
        st.sentences = list(p.sentences)
        st.shown = {k: v for k, v in st.shown.items() if k < len(st.sentences) and st.sentences[k] == v[0]}
        self._draw(i, key)
        return [(i, key, k, st.sentences[k]) for k in range(st.done)
                if k not in st.shown and (i, key, k, st.sentences[k]) not in self._inflight]

    def _draw(self, i: int, key: str) -> None:
        st = self._blocks.get((i, key))
        if st is None:
            return
        if st.kind == "name":
            text = st.sentences[0] if st.sentences else ""
        else:
            text = " ".join(st.shown[k][1] for k in range(st.done) if k in st.shown)
        if text == st.drawn:
            return
        st.drawn = text
        if text:
            x, y = self.regions[i][0], self.regions[i][1]
            self._overlays[i].set_block(key, text, st.box, (x, y), st.kind, font_px=st.font_px, colors=st.colors)
        else:
            self._overlays[i].remove_block(key)

    def on_partial(self, job_id: int, segments_per_region: list) -> None:
        request = self._requests.get(job_id)
        if not self.running or request is None:
            return
        flat = [s for g in segments_per_region for s in g]
        touched = set()
        for (i, key, k, src), seg in zip(request, flat):
            st = self._blocks.get((i, key))
            if st is None or not seg.translation or seg.translation == "…" or k >= len(st.sentences) \
                    or st.sentences[k] != src:
                continue
            st.shown[k] = (src, seg.translation)
            touched.add((i, key))
        for i, key in touched:
            self._draw(i, key)
        self.last_segments = flat

    def shown_segments(self) -> list:
        """Every translated sentence on screen now (for "edit the last translation")."""
        from app.pipeline import Segment

        out = []
        for st in self._blocks.values():
            for k in range(st.done):
                if st.kind == "text" and k in st.shown:
                    out.append(Segment("text", st.shown[k][0], st.shown[k][1], st.box))
        return out

    def apply_correction(self, source: str, corrected: str) -> None:
        """The user fixed a sentence: redraw every block showing it."""
        for (i, key), st in self._blocks.items():
            hit = [k for k, (src, _) in st.shown.items() if src == source]
            for k in hit:
                st.shown[k] = (source, corrected)
            if hit:
                self._draw(i, key)

    def on_job_done(self, job_id: int, segments=None) -> None:
        self._finish(job_id)

    def on_job_failed(self, job_id: int, why: str) -> None:
        self._ocr_final.pop(job_id, None)
        self._ocr_images.pop(job_id, None)
        if job_id == self.ocr_job:
            self.ocr_job = None
        self._finish(job_id)  # sentences not shown are requested again on the next OCR

    def _finish(self, job_id: int) -> None:
        for item in self._requests.pop(job_id, []):
            self._inflight.discard(item)
