"""Live 4b: translations drawn over each text block, sentence by sentence while the text types."""
from PIL import Image

from app.live.controller import LiveController
from app.live.machine import LiveParams
from app.pipeline import Segment
from app.text.postprocess import Paragraph, split_sentences

BLACK = Image.new("RGB", (400, 80), (0, 0, 0))
WHITE = Image.new("RGB", (400, 80), (255, 255, 255))
REGION = (100, 500, 400, 80)
PARAMS = LiveParams(partial_interval_ms=500)


class Script:
    """capture() returns images from a list (last one repeats); can raise for off-screen regions."""

    def __init__(self, frames):
        self.frames = list(frames)

    def __call__(self, x, y, w, h):
        f = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        if isinstance(f, Exception):
            raise f
        return f


class FakeOverlay:
    def __init__(self):
        self.blocks = {}
        self.closed = False
        self.draws = 0

    def set_block(self, key, text, box, origin, kind="text", font_px=None, colors=None):
        self.blocks[key] = text
        self.styles = getattr(self, "styles", {})
        self.styles[key] = (font_px, colors)
        self.draws += 1

    def remove_block(self, key):
        self.blocks.pop(key, None)

    def close(self):
        self.closed = True


def make(frames, scope="region", regions=(REGION,), params=PARAMS):
    jobs, notes, overlays = [], [], []
    ids = iter(range(1, 1000))

    def overlay_factory(region):
        o = FakeOverlay()
        overlays.append(o)
        return o

    c = LiveController(params, capture=Script(frames), submit=jobs.append, next_id=lambda: next(ids),
                       notify=notes.append, overlay_factory=overlay_factory, scope=scope, use_timer=False)
    c.start(list(regions))
    return c, jobs, notes, overlays


def para(text, top=0):
    return Paragraph("text", text, split_sentences(text), 0, top, 300, top + 20)


def drive(c, start, until, step=100):
    for t in range(start, until + 1, step):
        c.tick(t)


def ocr_jobs(jobs):
    return [j for j in jobs if j.mode == "live_ocr"]


def translate_jobs(jobs):
    return [j for j in jobs if j.mode == "live_translate"]


def sources(job):
    return [p.text for ps in job.paragraphs for p in ps]


def translate(c, job):
    """Worker stand-in: translate every sentence of the job, emit partial then done."""
    segs = [[Segment("text", p.text, "VI " + p.text, (p.left, p.top, p.right, p.bottom)) for p in ps]
            for ps in job.paragraphs]
    c.on_partial(job.id, segs)
    c.on_job_done(job.id, [s for g in segs for s in g])


def test_still_screen_ocrs_once_at_start_then_never():
    c, jobs, _, _ = make([BLACK])
    drive(c, 0, 3000)
    assert len(ocr_jobs(jobs)) == 1


def test_sentences_appear_while_the_text_is_typing():
    frames = [BLACK, WHITE] * 8 + [WHITE] * 30  # typing for ~1.5 s, then still
    c, jobs, _, overlays = make(frames)
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[]])  # initial OCR: nothing yet
    drive(c, 100, 600)
    partial = ocr_jobs(jobs)[-1]
    assert partial.id != ocr_jobs(jobs)[0].id  # a partial OCR while still typing
    c.on_ocr_done(partial.id, [[para("Where are you going? The")]])
    tr = translate_jobs(jobs)[-1]
    assert sources(tr) == ["Where are you going?"]  # the finished sentence only
    translate(c, tr)
    assert list(overlays[0].blocks.values()) == ["VI Where are you going?"]
    drive(c, 700, 2500)
    final = ocr_jobs(jobs)[-1]
    c.on_ocr_done(final.id, [[para("Where are you going? The station is closed today.")]])
    tr2 = translate_jobs(jobs)[-1]
    assert sources(tr2) == ["The station is closed today."]  # sentence 1 is not sent again
    translate(c, tr2)
    assert list(overlays[0].blocks.values()) == ["VI Where are you going? VI The station is closed today."]


def test_unchanged_block_is_not_translated_again():
    c, jobs, _, _ = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    translate(c, translate_jobs(jobs)[-1])
    n = len(translate_jobs(jobs))
    c.ocr_job = 99
    c._ocr_final[99] = True
    c.on_ocr_done(99, [[para("Hello.")]])
    assert len(translate_jobs(jobs)) == n


def test_gone_block_is_removed_from_the_overlay():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    translate(c, translate_jobs(jobs)[-1])
    c.ocr_job = 99
    c._ocr_final[99] = True
    c.on_ocr_done(99, [[]])
    assert overlays[0].blocks == {}


def test_superseded_translation_is_requested_again():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    lost = translate_jobs(jobs)[-1]
    c.on_job_failed(lost.id, "superseded")
    c.ocr_job = 99
    c._ocr_final[99] = True
    c.on_ocr_done(99, [[para("Hello.")]])
    assert sources(translate_jobs(jobs)[-1]) == ["Hello."] and translate_jobs(jobs)[-1].id != lost.id


def test_screen_scope_rate_limits_ocr():
    c, jobs, _, _ = make([BLACK, WHITE] * 30, scope="screen")
    drive(c, 0, 4000)
    assert 1 <= len(ocr_jobs(jobs)) <= 5


def test_stop_closes_overlays_and_ignores_late_results():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hi.")]])
    tr = translate_jobs(jobs)[-1]
    c.stop()
    translate(c, tr)
    assert all(o.closed for o in overlays) and overlays[0].blocks == {}


def test_off_screen_region_is_skipped_and_reported_once():
    c, jobs, notes, _ = make([OSError("monitor gone")])
    drive(c, 0, 1000)
    assert len(notes) == 1 and jobs == []


def test_failed_region_keeps_its_slot():
    shots = iter([OSError("gone"), BLACK] * 50)

    def capture(x, y, w, h):
        v = next(shots)
        if isinstance(v, Exception):
            raise v
        return v

    jobs = []
    c = LiveController(PARAMS, capture=capture, submit=jobs.append, next_id=iter(range(1, 99)).__next__,
                       notify=lambda m: None, overlay_factory=lambda r: FakeOverlay(), use_timer=False)
    c.start([(0, 0, 10, 10), (0, 20, 10, 10)])
    c.tick(0)
    assert ocr_jobs(jobs)[0].images[0] is None and ocr_jobs(jobs)[0].images[1] is not None


def test_name_line_is_shown_untranslated():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    name = Paragraph("name", "Druvis III", [], 0, 0, 100, 20)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[name, para("Hello.", 30)]])
    assert sources(translate_jobs(jobs)[-1]) == ["Hello."]
    assert "Druvis III" in overlays[0].blocks.values()


# ---- 4b Task 5: regions relative to the game window, ignore regions ----------------------------------
class Window:
    def __init__(self, frame):
        self.frame = frame

    def __call__(self):
        return self.frame


def make_rel(frames, window, rel, ignore=(), on_screen=lambda r: True):
    jobs, notes, shots = [], [], []
    script = Script(frames)

    def capture(x, y, w, h):
        shots.append((x, y, w, h))
        return script(x, y, w, h)

    c = LiveController(PARAMS, capture=capture, submit=jobs.append, next_id=iter(range(1, 999)).__next__,
                       notify=notes.append, overlay_factory=lambda r: FakeOverlay(), use_timer=False,
                       on_screen=on_screen)
    c.start_relative(list(rel), window, list(ignore))
    return c, jobs, notes, shots


def test_regions_follow_the_game_window():
    win = Window((100, 50, 1000, 500))
    c, jobs, _, shots = make_rel([BLACK], win, [(0.1, 0.8, 0.8, 0.2)])
    c.tick(0)
    assert shots[-1] == (200, 450, 800, 100)
    win.frame = (400, 300, 1000, 500)
    c.tick(300)
    assert shots[-1] == (500, 700, 800, 100)
    assert len(ocr_jobs(jobs)) == 2  # the window moved: what is there now is read again


def test_minimized_game_pauses_live_and_reports_once():
    win = Window(None)
    c, jobs, notes, shots = make_rel([BLACK], win, [(0, 0, 1, 1)])
    for t in range(0, 2000, 300):
        c.tick(t)
    assert jobs == [] and shots == [] and len(notes) == 1


def test_ignore_region_covering_everything_means_no_change():
    win = Window((0, 0, 400, 80))
    c, jobs, _, _ = make_rel([BLACK, WHITE] * 30, win, [(0, 0, 1, 1)], ignore=[(0, 0, 1, 1)])
    for t in range(0, 3000, 100):
        c.tick(t)
    assert len(ocr_jobs(jobs)) == 1  # the start-up read only: the blinking is ignored


def test_region_outside_every_screen_is_reported_once():
    win = Window((5000, 5000, 400, 80))
    c, jobs, notes, shots = make_rel([BLACK], win, [(0, 0, 1, 1)], on_screen=lambda r: False)
    for t in range(0, 1000, 300):
        c.tick(t)
    assert jobs == [] and shots == [] and len(notes) == 1


def test_shown_segments_and_apply_correction():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello. Bye.")]])
    translate(c, translate_jobs(jobs)[-1])
    assert [(s.source, s.translation) for s in c.shown_segments()] == [("Hello.", "VI Hello."), ("Bye.", "VI Bye.")]
    c.apply_correction("Hello.", "Chào.")
    assert list(overlays[0].blocks.values()) == ["Chào. VI Bye."]



def _boxed(bg, fg):
    """400x80 image: a 300x30 text box at (0, 0) with `fg` strokes on `bg`."""
    img = Image.new("RGB", (400, 80), (90, 90, 90))
    box = Image.new("RGB", (300, 30), bg)
    for x in range(10, 290, 6):
        box.paste(fg, (x, 8, x + 3, 22))
    img.paste(box, (0, 0))
    return img


def test_match_style_uses_the_source_font_size_and_colours():
    c, jobs, _, overlays = make([_boxed((250, 250, 250), (20, 20, 20))])
    c.tick(0)
    p = Paragraph("text", "Hello.", ["Hello."], 0, 0, 300, 30, line_height=30)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[p]])
    translate(c, translate_jobs(jobs)[-1])
    font_px, colors = overlays[0].styles[next(iter(overlays[0].blocks))]
    assert font_px == 24
    assert colors is not None and max(colors.text) < 40 and min(colors.bg) > 230


def test_classic_style_keeps_the_font_size_but_not_the_colours():
    jobs, overlays = [], []

    def factory(r):
        overlays.append(FakeOverlay())
        return overlays[-1]

    c = LiveController(PARAMS, capture=Script([_boxed((250, 250, 250), (20, 20, 20))]), submit=jobs.append,
                       next_id=iter(range(1, 99)).__next__, notify=lambda m: None, overlay_factory=factory,
                       use_timer=False, style="classic")
    c.start([REGION])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[Paragraph("text", "Hi.", ["Hi."], 0, 0, 300, 30, line_height=30)]])
    translate(c, translate_jobs(jobs)[-1])
    assert overlays[0].styles[next(iter(overlays[0].blocks))] == (24, None)
