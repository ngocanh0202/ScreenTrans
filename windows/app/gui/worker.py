"""Background translation: one worker thread owns the only Pipeline (Phase 1 single-thread contract)."""
import threading
import traceback
from dataclasses import dataclass
from typing import Callable, Literal

from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.pipeline import Pipeline
from app.text.postprocess import postprocess

SUPERSEDED = "superseded"
PipelineFactory = Callable[[Callable[[int, int], None]], Pipeline]


@dataclass
class Job:
    id: int
    mode: Literal["region", "fullscreen", "live_ocr", "live_translate", "correct", "set_game"]
    image: Image.Image | None
    origin: tuple[int, int]  # physical top-left of the image on the virtual screen
    images: list | None = None       # live_ocr: one image per watched region
    paragraphs: list | None = None   # live_translate: list of paragraphs per region
    payload: dict | None = None      # correct: {"corrections": [[src, machine, fixed]], "terms": [[src, target|None]]}
                                     # set_game: {"game": id, "glossaries": [paths], "overrides": {src: fixed}}


CONTROL = ("correct", "set_game")  # never superseded, run before anything else


class TranslationWorker(QObject):
    ready = Signal()
    failed = Signal(str)
    progress = Signal(int, int)
    job_started = Signal(int)
    segment = Signal(int, object)
    job_done = Signal(int, object)
    job_failed = Signal(int, str)
    ocr_done = Signal(int, object)   # live_ocr: list[list[Paragraph]] per region
    partial = Signal(int, object)    # live_translate: list[list[Segment]] per region, after each sentence
    _wake = Signal()

    def __init__(self, factory: PipelineFactory):
        super().__init__()
        self._factory = factory
        self._pipeline: Pipeline | None = None
        self._lock = threading.Lock()
        self._pending: Job | None = None
        self._live_pending: Job | None = None  # Live jobs have their own slot: they never replace user jobs
        self._control: list[Job] = []
        self.is_ready = False
        self.error: str | None = None
        self._wake.connect(self._process)

    @Slot()
    def start(self) -> None:
        try:
            pipeline = self._factory(self.progress.emit)
            warm_up = getattr(pipeline.translator, "warm_up", None)
            if callable(warm_up):
                warm_up()
        except Exception as e:  # any load failure is shown to the user, the app keeps running
            self.error = str(e) or type(e).__name__
            self.failed.emit(self.error)
            self._process()
            return
        self._pipeline = pipeline
        self.is_ready = True
        self.ready.emit()
        self._process()

    def submit(self, job: Job) -> None:
        """Thread-safe. Keeps only the newest waiting job of its kind (user / live); an older waiting
        one of the same kind is superseded. User jobs run first."""
        with self._lock:
            if job.mode in CONTROL:
                self._control.append(job)
                old = None
            elif job.mode.startswith("live_"):
                old, self._live_pending = self._live_pending, job
            else:
                old, self._pending = self._pending, job
        if old is not None:
            self.job_failed.emit(old.id, SUPERSEDED)
        self._wake.emit()

    def _take(self) -> Job | None:
        with self._lock:
            if self._control:
                return self._control.pop(0)
            if self._pending is not None:
                job, self._pending = self._pending, None
            else:
                job, self._live_pending = self._live_pending, None
        return job

    @Slot()
    def _process(self) -> None:
        if self.error is not None:
            while (job := self._take()) is not None:
                self.job_failed.emit(job.id, self.error)
            return
        if not self.is_ready:
            return
        while (job := self._take()) is not None:
            self._run(job)

    def _run(self, job: Job) -> None:
        self.job_started.emit(job.id)
        try:
            if job.mode == "correct":
                for src, machine, fixed in job.payload.get("corrections", []):
                    self._pipeline.correct(src, machine, fixed)
                for src, target in job.payload.get("terms", []):
                    self._pipeline.glossary.add_entry(src, target)
                self.job_done.emit(job.id, [])
                return
            if job.mode == "set_game":
                from pathlib import Path

                from app.glossary import Glossary

                glossary = Glossary.load(*(Path(g) for g in job.payload.get("glossaries", [])))
                self._pipeline.set_game(job.payload.get("game"), glossary, job.payload.get("overrides", {}))
                self.job_done.emit(job.id, [])
                return
            if job.mode == "live_ocr":
                per_region = [postprocess(self._pipeline.ocr.recognize(img)) if img is not None else None
                              for img in job.images or []]  # None: that region could not be captured
                self.ocr_done.emit(job.id, per_region)
                return
            if job.mode == "live_translate":
                groups = job.paragraphs or []
                flat = [p for ps in groups for p in ps]
                sizes = [len(ps) for ps in groups]

                def regroup(segs):
                    out, i = [], 0
                    for n in sizes:
                        out.append(segs[i:i + n])
                        i += n
                    return out

                last = [[] for _ in groups]
                for segs in self._pipeline.iter_sentences(flat):
                    last = regroup(segs)
                    self.partial.emit(job.id, last)
                self.job_done.emit(job.id, last)
                return
            if job.mode == "fullscreen":
                paragraphs = postprocess(self._pipeline.ocr.recognize(job.image))
                segments = []
                for seg in self._pipeline.iter_segments(paragraphs):
                    segments.append(seg)
                    self.segment.emit(job.id, seg)
            else:
                segments = self._pipeline.run(job.image).segments
        except Exception as e:
            traceback.print_exc()
            self.job_failed.emit(job.id, str(e) or type(e).__name__)
            return
        self.job_done.emit(job.id, segments)


def start_worker(
    factory: PipelineFactory, connect: Callable[[TranslationWorker], None] | None = None
) -> tuple[QThread, TranslationWorker]:
    """Create the worker thread. All signal connections must be made in `connect`, before the
    thread starts: connecting/disconnecting while the worker emits crashes PySide6 (seen in tests)."""
    thread = QThread()
    worker = TranslationWorker(factory)
    worker.moveToThread(thread)
    if connect is not None:
        connect(worker)
    thread.started.connect(worker.start)
    thread.start()
    return thread, worker
