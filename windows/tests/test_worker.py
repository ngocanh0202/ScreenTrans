import time

import pytest
from PIL import Image

from app.cache import TranslationCache
from app.glossary import Glossary
from app.gui.worker import Job, TranslationWorker, start_worker
from app.ocr.base import Line
from app.pipeline import Pipeline
from app.translate.base import ModelNotFound
from fakes import FakeOcr, FakeTranslator

IMG = Image.new("RGB", (10, 10))
LINES = [Line("Druvis Ill", 37, 13, 149, 29), Line("Hello there.", 26, 78, 500, 31),
         Line("Far below.", 26, 300, 300, 31)]


def _factory(delay=0.0, fail=None):
    def factory(progress):
        if fail:
            raise fail
        progress(5, 10)
        tr = FakeTranslator(lambda s: (time.sleep(delay), "VI " + s)[1])
        return Pipeline(FakeOcr(LINES), tr, Glossary([]), TranslationCache(100, None))
    return factory


class Recorder:
    """Collects worker signals; connected before the thread starts (no cross-thread connect races)."""

    def __init__(self):
        self.events = []

    def attach(self, w: TranslationWorker) -> None:
        w.ready.connect(lambda: self.events.append(("ready",)))
        w.failed.connect(lambda msg: self.events.append(("failed", msg)))
        w.segment.connect(lambda i, seg: self.events.append(("segment", i, seg.source)))
        w.job_done.connect(lambda i, segs: self.events.append(("done", i, segs)))
        w.job_failed.connect(lambda i, why: self.events.append(("job_failed", i, why)))
        w.job_started.connect(lambda i: self.events.append(("started", i)))

    def of(self, kind):
        return [e for e in self.events if e[0] == kind]


@pytest.fixture
def run_worker(qtbot):
    threads = []

    def make(**kw):
        rec = Recorder()
        thread, w = start_worker(_factory(**kw), connect=rec.attach)
        threads.append(thread)
        return w, rec

    yield make
    for thread in threads:
        thread.quit()
        assert thread.wait(5000)


def test_ready_then_region_job(qtbot, run_worker):
    w, rec = run_worker()
    w.submit(Job(1, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: bool(rec.of("done")), timeout=5000)
    _, job_id, segments = rec.of("done")[0]
    assert job_id == 1
    assert [s.kind for s in segments] == ["name", "text", "text"]
    assert segments[1].translation == "VI Hello there."


def test_progress_and_ready_signals():
    w = TranslationWorker(_factory())
    events = []
    w.progress.connect(lambda done, total: events.append(("progress", done, total)))
    w.ready.connect(lambda: events.append(("ready",)))
    w.start()
    assert events == [("progress", 5, 10), ("ready",)]


def test_fullscreen_emits_segments_progressively(qtbot, run_worker):
    w, rec = run_worker()
    w.submit(Job(7, "fullscreen", IMG, (0, 0)))
    qtbot.waitUntil(lambda: bool(rec.of("done")), timeout=5000)
    assert rec.of("segment") == [("segment", 7, "Druvis III"), ("segment", 7, "Hello there."),
                                 ("segment", 7, "Far below.")]
    assert rec.events.index(rec.of("segment")[-1]) < rec.events.index(rec.of("done")[0])


def test_only_latest_pending_job_runs(qtbot, run_worker):
    w, rec = run_worker(delay=0.3)
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: ("started", 1) in rec.events, timeout=5000)  # job 1 is now running
    w.submit(Job(2, "region", IMG, (0, 0)))
    w.submit(Job(3, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: any(e[1] == 3 for e in rec.of("done")), timeout=10000)
    assert ("job_failed", 2, "superseded") in rec.events
    assert [e[1] for e in rec.of("done")] == [1, 3]


def test_factory_failure_reports_and_fails_jobs(qtbot, run_worker):
    w, rec = run_worker(fail=ModelNotFound("no model here"))
    qtbot.waitUntil(lambda: bool(rec.of("failed")), timeout=5000)
    assert "no model here" in rec.of("failed")[0][1]
    w.submit(Job(4, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: bool(rec.of("job_failed")), timeout=5000)
    assert rec.of("job_failed")[0][1] == 4 and "no model here" in rec.of("job_failed")[0][2]


def test_job_submitted_before_ready_still_runs():
    w = TranslationWorker(_factory())
    done = []
    w.job_done.connect(lambda i, segs: done.append(i))
    w.submit(Job(9, "region", IMG, (0, 0)))
    w.start()
    assert done == [9]
