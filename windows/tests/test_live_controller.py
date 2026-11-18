from PIL import Image

from app.live.controller import LiveController
from app.live.machine import LiveParams
from app.pipeline import Segment
from app.text.postprocess import Paragraph

BLACK = Image.new("RGB", (400, 80), (0, 0, 0))
WHITE = Image.new("RGB", (400, 80), (255, 255, 255))
REGION = (100, 500, 400, 80)


class Script:
    """capture() returns images from a list (last one repeats); can raise for off-screen regions."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.calls = 0

    def __call__(self, x, y, w, h):
        self.calls += 1
        f = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        if isinstance(f, Exception):
            raise f
        return f


class FakeOverlay:
    def __init__(self):
        self.shown = None
        self.closed = False

    def show_segments(self, segments):
        self.shown = segments

    def close(self):
        self.closed = True


def make(frames, area=False):
    jobs, notes, overlays = [], [], []
    ids = iter(range(1, 1000))

    def overlay_factory(region):
        o = FakeOverlay()
        overlays.append(o)
        return o

    c = LiveController(LiveParams(), capture=Script(frames), submit=jobs.append, next_id=lambda: next(ids),
                       notify=notes.append, overlay_factory=overlay_factory, area=area, use_timer=False)
    return c, jobs, notes, overlays


def drive(c, until_ms, step=100):
    for t in range(0, until_ms + 1, step):
        c.tick(t)


def test_typing_then_still_gives_one_ocr_job():
    frames = [BLACK, WHITE, BLACK, WHITE, BLACK] + [BLACK] * 20  # changes for 400 ms then still
    c, jobs, _, _ = make(frames)
    c.start([REGION])
    drive(c, 1500)
    assert [j.mode for j in jobs] == ["live_ocr", "live_ocr"]  # initial + after typing settles
    assert len(jobs[-1].images) == 1


def test_still_screen_ocrs_once_at_start_then_never():
    c, jobs, _, _ = make([BLACK])
    c.start([REGION])
    drive(c, 3000)
    assert [j.mode for j in jobs] == ["live_ocr"]  # the line already on screen is translated (I4)


def test_ocr_text_is_translated_progressively_into_the_overlay():
    c, jobs, _, overlays = make([BLACK, WHITE] + [WHITE] * 10)
    c.start([REGION])
    drive(c, 800)
    ocr = jobs[-1]
    para = Paragraph("text", "Hello there.", ["Hello there."], 0, 0, 100, 20)
    c.on_ocr_done(ocr.id, [[para]])
    tr = jobs[-1]
    assert tr.mode == "live_translate" and tr.paragraphs == [[para]]
    seg = Segment("text", "Hello there.", "Xin chào.", (0, 0, 100, 20))
    c.on_partial(tr.id, [[seg]])
    assert overlays[0].shown == [seg]


def test_same_text_is_not_translated_twice():
    c, jobs, _, _ = make([BLACK, WHITE] + [WHITE] * 10)
    c.start([REGION])
    drive(c, 800)
    para = Paragraph("text", "Hello.", ["Hello."], 0, 0, 100, 20)
    c.on_ocr_done(jobs[-1].id, [[para]])
    n = len(jobs)
    c.machine.state = "idle"
    c.ocr_job = 99
    c.on_ocr_done(99, [[para]])
    assert len(jobs) == n


def test_stop_ignores_late_results_and_closes_overlays():
    c, jobs, _, overlays = make([BLACK, WHITE] + [WHITE] * 10)
    c.start([REGION])
    drive(c, 800)
    c.on_ocr_done(jobs[-1].id, [[Paragraph("text", "Hi.", ["Hi."], 0, 0, 10, 10)]])
    tr = jobs[-1]
    c.stop()
    c.on_partial(tr.id, [[Segment("text", "Hi.", "Chào.", (0, 0, 10, 10))]])
    assert all(o.closed for o in overlays)
    assert all(o.shown is None for o in overlays)


def test_off_screen_region_is_skipped_and_reported_once():
    c, jobs, notes, _ = make([OSError("monitor gone")])
    c.start([REGION])
    drive(c, 1000)
    assert len(notes) == 1 and jobs == []


def test_area_mode_rate_limits_ocr_and_translates_only_new_blocks():
    frames = [BLACK, WHITE] * 20  # constantly changing
    c, jobs, _, _ = make(frames, area=True)
    c.start([REGION])
    drive(c, 4000)
    ocr_times = [j for j in jobs if j.mode == "live_ocr"]
    assert 1 <= len(ocr_times) <= 3  # max_wait 2 s and at most one OCR per second
    a = Paragraph("text", "Bubble one.", ["Bubble one."], 0, 0, 100, 20)
    c.on_ocr_done(ocr_times[-1].id, [[a]])
    first_tr = [j for j in jobs if j.mode == "live_translate"]
    assert len(first_tr) == 1 and first_tr[0].paragraphs == [[a]]
    c.ocr_job = 500
    c.on_ocr_done(500, [[a]])  # same bubble again: nothing new to translate
    assert len([j for j in jobs if j.mode == "live_translate"]) == 1


def test_superseded_translation_is_retried_on_the_next_identical_ocr():
    c, jobs, _, _ = make([BLACK, WHITE] + [WHITE] * 10)
    c.start([REGION])
    drive(c, 800)
    para = Paragraph("text", "Hello.", ["Hello."], 0, 0, 100, 20)
    c.on_ocr_done(jobs[-1].id, [[para]])
    tr = jobs[-1]
    c.on_job_failed(tr.id, "superseded")
    c.ocr_job = 99
    c.on_ocr_done(99, [[para]])
    assert jobs[-1].mode == "live_translate" and jobs[-1].id != tr.id


def test_area_failed_translation_makes_its_blocks_new_again():
    c, jobs, _, _ = make([BLACK], area=True)
    c.start([REGION])
    drive(c, 0)
    a = Paragraph("text", "Bubble one.", ["Bubble one."], 0, 0, 100, 20)
    c.on_ocr_done(jobs[-1].id, [[a]])
    tr = jobs[-1]
    c.on_job_failed(tr.id, "superseded")
    c.ocr_job = 500
    c.on_ocr_done(500, [[a]])
    assert jobs[-1].mode == "live_translate" and jobs[-1].id != tr.id
