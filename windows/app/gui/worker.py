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
    notice = Signal(str)             # something the user should know (an OCR engine could not load)
    _wake = Signal()

    def __init__(self, factory: PipelineFactory):
        super().__init__()
        self._factory = factory
        self._pipeline: Pipeline | None = None
        self._lock = threading.Lock()
        self._pending: Job | None = None
        self._live_pending: dict[str, Job] = {}  # one waiting slot per Live job kind: never replace user jobs
        self._control: list[Job] = []
        self.is_ready = False
        self.error: str | None = None
        self._wake.connect(self._process)
        # Live OCR runs on its own thread with its own OCR engine: a slow (remote) translation never stops Live
        # from reading the screen. One waiting slot, like the other Live jobs.
        self._ocr_cv = threading.Condition()
        self._ocr_slot: Job | None = None
        self._live_ocr = None
        threading.Thread(target=self._ocr_loop, name="live-ocr", daemon=True).start()

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
            with self._ocr_cv:
                self._ocr_cv.notify_all()
            self._process()
            return
        self._pipeline = pipeline
        self._fast_ocr = pipeline.ocr  # Live always reads with the fast default engine
        self._live_ocr = self._own_ocr(pipeline.ocr)
        self._local = pipeline.translator  # the local model: default engine and fallback of the remote ones
        self._translators: dict = {}
        self._no_key_noticed: set[str] = set()
        self._engines: dict = {}
        self.is_ready = True
        self.ready.emit()
        with self._ocr_cv:
            self._ocr_cv.notify_all()
        self._process()

    def submit(self, job: Job) -> None:
        """Thread-safe. Keeps only the newest waiting job of its kind (user / live); an older waiting
        one of the same kind is superseded. User jobs run first."""
        if job.mode == "live_ocr":
            with self._ocr_cv:
                old, self._ocr_slot = self._ocr_slot, job
                self._ocr_cv.notify_all()
            if old is not None:
                self.job_failed.emit(old.id, SUPERSEDED)
            return
        with self._lock:
            if job.mode in CONTROL:
                self._control.append(job)
                old = None
            elif job.mode.startswith("live_"):
                old, self._live_pending[job.mode] = self._live_pending.get(job.mode), job
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
                job = None
                for mode in ("live_translate", "live_ocr"):  # finish shown sentences first
                    if mode in self._live_pending:
                        job = self._live_pending.pop(mode)
                        break
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

    @staticmethod
    def _own_ocr(ocr):
        """A separate Windows OCR instance for the Live OCR thread (never shared across threads)."""
        try:
            from app.ocr.windows_ocr import WindowsOcr

            if isinstance(ocr, WindowsOcr):
                return WindowsOcr()
        except Exception:
            pass
        return ocr

    def _ocr_loop(self) -> None:
        while True:
            with self._ocr_cv:
                while self._ocr_slot is None or not (self.is_ready or self.error is not None):
                    self._ocr_cv.wait()
                job, self._ocr_slot = self._ocr_slot, None
            if self.error is not None:
                self.job_failed.emit(job.id, self.error)
                continue
            self.job_started.emit(job.id)
            try:
                per_region = [postprocess(self._live_ocr.recognize(img)) if img is not None else None
                              for img in job.images or []]  # None: that region could not be captured
            except Exception as e:
                traceback.print_exc()
                self.job_failed.emit(job.id, str(e) or type(e).__name__)
                continue
            self.ocr_done.emit(job.id, per_region)

    def _use_ocr(self, name: str) -> None:
        """The game's OCR engine for one-shot translations; falls back to the default if it cannot load."""
        if name in ("auto", "windows", None):
            self._pipeline.ocr = self._fast_ocr
            return
        if name not in self._engines:
            from app.ocr import engines

            try:
                self._engines[name] = engines.create(name)
            except Exception as e:  # missing package / model: keep working with the default engine
                self._engines[name] = None
                label = next((x.label for x in engines.WINDOWS if x.name == name), name)
                self.notice.emit(f"{label.split(' —')[0]} không dùng được ({e}); dùng Windows OCR.")
        self._pipeline.ocr = self._engines[name] or self._fast_ocr

    def _use_engine(self, engine: str, llm: dict, game: str | None = None) -> None:
        """The game's translation engine: the local model, or a remote LLM that falls back to it."""
        from app.translate import remote

        try:
            self._switch_engine(engine, llm, game)
        except Exception:  # e.g. a package missing from the build: never block the game, never show the error
            traceback.print_exc()
            self._pipeline.translator = self._local
            self.notice.emit(f"Không bật được {remote.NAMES.get(engine, engine)} — dùng model trên máy.")

    def _switch_engine(self, engine: str, llm: dict, game: str | None) -> None:
        from app.translate import remote

        if engine not in remote.NAMES:
            self._pipeline.translator = self._local
            return
        import hashlib
        from pathlib import Path

        from app.secrets import KeyStore
        from app.translate.context_store import ContextStore
        from app.translate.llm import LlmTranslator
        from app.usage import Usage

        data_dir = Path(llm.get("data_dir") or ".")
        key = KeyStore(data_dir).get(engine)
        if not key:
            self._pipeline.translator = self._local
            if engine not in self._no_key_noticed:
                self._no_key_noticed.add(engine)
                self.notice.emit(f"Chưa nhập key cho {remote.NAMES[engine]} — dùng model trên máy.")
            return
        self._no_key_noticed.discard(engine)
        model, url = llm.get("model", ""), llm.get("url", "")
        limit = int(llm.get("daily_limit") or 50000)
        cache_key = (engine, model, url, hashlib.sha256(key.encode()).hexdigest(), limit, str(data_dir))
        tr = self._translators.get(cache_key)
        if tr is None:
            tr = LlmTranslator(engine, remote.make_client(engine, key, model=model, url=url), self._local,
                               Usage(data_dir), limit, self.notice.emit, contexts=ContextStore(data_dir))
            self._translators[cache_key] = tr
        tr.set_game(game, str(llm.get("notes") or ""), self._pipeline.examples())
        self._pipeline.translator = tr

    def _run(self, job: Job) -> None:
        self.job_started.emit(job.id)
        if hasattr(self._pipeline.translator, "timeout_s"):  # remote engine: Live must not stall
            self._pipeline.translator.timeout_s = 2.5 if job.mode == "live_translate" else 6.0
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
                self._use_ocr(job.payload.get("ocr", "auto"))
                self._use_engine(job.payload.get("engine", "local"), job.payload.get("llm") or {},
                                 job.payload.get("game"))
                self.job_done.emit(job.id, [])
                return
            if job.mode == "live_ocr":
                per_region = [postprocess(self._fast_ocr.recognize(img)) if img is not None else None
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
                for segs in self._pipeline.iter_sentences(flat, speaker=(job.payload or {}).get("speaker")):
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
