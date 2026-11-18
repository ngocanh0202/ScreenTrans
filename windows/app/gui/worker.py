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
    mode: Literal["region", "fullscreen"]
    image: Image.Image
    origin: tuple[int, int]  # physical top-left of the image on the virtual screen


class TranslationWorker(QObject):
    ready = Signal()
    failed = Signal(str)
    progress = Signal(int, int)
    job_started = Signal(int)
    segment = Signal(int, object)
    job_done = Signal(int, object)
    job_failed = Signal(int, str)
    _wake = Signal()

    def __init__(self, factory: PipelineFactory):
        super().__init__()
        self._factory = factory
        self._pipeline: Pipeline | None = None
        self._lock = threading.Lock()
        self._pending: Job | None = None
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
        """Thread-safe. Keeps only the newest waiting job; an older waiting one is superseded."""
        with self._lock:
            old, self._pending = self._pending, job
        if old is not None:
            self.job_failed.emit(old.id, SUPERSEDED)
        self._wake.emit()

    def _take(self) -> Job | None:
        with self._lock:
            job, self._pending = self._pending, None
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
