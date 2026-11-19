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


def test_live_ocr_returns_paragraphs_per_image(qtbot, run_worker):
    w, rec = run_worker()
    got = []
    w.ocr_done.connect(lambda i, per: got.append((i, per)))
    w.submit(Job(3, "live_ocr", None, (0, 0), images=[IMG, IMG]))
    qtbot.waitUntil(lambda: bool(got), timeout=5000)
    job_id, per = got[0]
    assert job_id == 3 and len(per) == 2
    assert [p.text for p in per[0]] == ["Druvis III", "Hello there.", "Far below."]


def test_live_translate_emits_partials_grouped_per_region(qtbot, run_worker):
    from app.text.postprocess import Paragraph

    w, rec = run_worker()
    parts = []
    w.partial.connect(lambda i, segs: parts.append(segs))
    a = Paragraph("text", "One.", ["One."], 0, 0, 10, 10)
    b = Paragraph("text", "Two.", ["Two."], 0, 20, 10, 30)
    w.submit(Job(4, "live_translate", None, (0, 0), paragraphs=[[a], [b]]))
    qtbot.waitUntil(lambda: bool(rec.of("done")), timeout=5000)
    assert len(parts) >= 2 and all(len(p) == 2 for p in parts)
    final = rec.of("done")[0][2]
    assert [[s.translation for s in g] for g in final] == [["VI One."], ["VI Two."]]


def test_live_jobs_never_supersede_user_jobs(qtbot, run_worker):
    w, rec = run_worker(delay=0.3)
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: ("started", 1) in rec.events, timeout=5000)  # job 1 is now running
    w.submit(Job(2, "region", IMG, (0, 0)))       # waits
    w.submit(Job(3, "live_ocr", None, (0, 0), images=[IMG]))
    w.submit(Job(4, "live_ocr", None, (0, 0), images=[IMG]))  # supersedes 3 only
    qtbot.waitUntil(lambda: len(rec.of("done")) == 2, timeout=10000)
    assert [e[1] for e in rec.of("job_failed")] == [3]
    assert sorted(e[1] for e in rec.of("done")) == [1, 2]


def test_live_ocr_keeps_an_empty_slot_for_a_missing_image(qtbot, run_worker):
    w, rec = run_worker()
    got = []
    w.ocr_done.connect(lambda i, per: got.append(per))
    w.submit(Job(5, "live_ocr", None, (0, 0), images=[None, IMG]))
    qtbot.waitUntil(lambda: bool(got), timeout=5000)
    assert got[0][0] is None and len(got[0][1]) == 3


def test_correct_and_set_game_jobs_are_never_superseded_and_apply_to_later_jobs(qtbot, run_worker, tmp_path):
    import json as _json

    w, rec = run_worker(delay=0.2)
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: ("started", 1) in rec.events, timeout=5000)
    w.submit(Job(2, "correct", None, (0, 0), payload={
        "corrections": [["Hello there.", "VI Hello there.", "Chào cậu."]], "terms": [["Arcanist", None]]}))
    gl = tmp_path / "g.json"
    gl.write_text(_json.dumps({"entries": []}), encoding="utf-8")
    w.submit(Job(3, "set_game", None, (0, 0), payload={
        "game": "b.exe", "glossaries": [str(gl)], "overrides": {"Far below.": "Tít dưới."}}))
    w.submit(Job(4, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: any(e[1] == 4 for e in rec.of("done")), timeout=10000)
    assert rec.of("job_failed") == []
    segs = [e for e in rec.of("done") if e[1] == 4][0][2]
    assert [s.translation for s in segs[1:]] == ["VI Hello there.", "Tít dưới."]  # set_game replaced overrides


def test_correct_job_overrides_the_next_translation(qtbot, run_worker):
    w, rec = run_worker()
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "correct", None, (0, 0), payload={"corrections": [["Hello there.", "x", "Chào cậu."]], "terms": []}))
    w.submit(Job(2, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: any(e[1] == 2 for e in rec.of("done")), timeout=5000)
    segs = [e for e in rec.of("done") if e[1] == 2][0][2]
    assert segs[1].translation == "Chào cậu."


def test_live_translate_does_not_supersede_a_waiting_live_ocr(qtbot, run_worker):
    w, rec = run_worker(delay=0.3)
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: ("started", 1) in rec.events, timeout=5000)
    w.submit(Job(2, "live_ocr", None, (0, 0), images=[IMG]))
    w.submit(Job(3, "live_translate", None, (0, 0), paragraphs=[[]]))
    qtbot.waitUntil(lambda: any(e[1] == 3 for e in rec.of("done")), timeout=10000)
    assert rec.of("job_failed") == []


def test_set_game_switches_the_ocr_engine_but_live_keeps_the_fast_one(qtbot, run_worker, monkeypatch):
    from app.ocr import engines
    from app.ocr.base import Line

    slow = FakeOcr([Line("Slow engine.", 0, 0, 100, 20)])
    monkeypatch.setattr(engines, "create", lambda name: slow)
    w, rec = run_worker()
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "set_game", None, (0, 0), payload={"game": "g", "glossaries": [], "overrides": {}, "ocr": "rapid"}))
    w.submit(Job(2, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: any(e[1] == 2 for e in rec.of("done")), timeout=5000)
    assert [s.source for s in [e for e in rec.of("done") if e[1] == 2][0][2]] == ["Slow engine."]
    got = []
    w.ocr_done.connect(lambda i, per: got.append(per))
    w.submit(Job(3, "live_ocr", None, (0, 0), images=[IMG]))
    qtbot.waitUntil(lambda: bool(got), timeout=5000)
    assert "Slow engine." not in [p.text for p in got[0][0]]  # Live: the fast default engine


def test_an_ocr_engine_that_fails_to_load_falls_back_with_a_notice(qtbot, run_worker, monkeypatch):
    from app.ocr import engines

    def boom(name):
        raise RuntimeError("no onnxruntime")

    monkeypatch.setattr(engines, "create", boom)
    w, rec = run_worker()
    notes = []
    w.notice.connect(notes.append)
    qtbot.waitUntil(lambda: w.is_ready, timeout=5000)
    w.submit(Job(1, "set_game", None, (0, 0), payload={"game": "g", "glossaries": [], "overrides": {}, "ocr": "rapid"}))
    w.submit(Job(2, "region", IMG, (0, 0)))
    qtbot.waitUntil(lambda: any(e[1] == 2 for e in rec.of("done")), timeout=5000)
    assert len(notes) == 1 and "RapidOCR" in notes[0]
