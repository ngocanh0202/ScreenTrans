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

    def set_block(self, key, text, box, origin, kind="text", font_px=None, colors=None, angle=0.0):
        self.blocks[key] = text
        self.styles = getattr(self, "styles", {})
        self.styles[key] = (font_px, colors)
        self.angles = getattr(self, "angles", {})
        self.angles[key] = angle
        self.draws += 1

    def remove_block(self, key):
        self.blocks.pop(key, None)

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


def make(frames, scope="region", regions=(REGION,), params=PARAMS, clock=None):
    jobs, notes, overlays = [], [], []
    ids = iter(range(1, 1000))

    def overlay_factory(region):
        o = FakeOverlay()
        overlays.append(o)
        return o

    c = LiveController(params, capture=Script(frames), submit=jobs.append, next_id=lambda: next(ids),
                       notify=notes.append, overlay_factory=overlay_factory, scope=scope, use_timer=False,
                       clock=clock or Clock())
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
    c.tick(600)  # it stood still for 300 ms after the move
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


# ---- final review fixes -------------------------------------------------------------------------------
def test_c1_typing_that_stops_just_before_max_wait_still_gets_a_final_read():
    frames = [BLACK, WHITE] * 10 + [WHITE] * 40  # changes until 1900 ms, then still
    c, jobs, _, _ = make(frames)
    for t in range(0, 4000, 100):
        c.tick(t)
        if c.ocr_job is not None:  # the worker answers at once with nothing new
            c.on_ocr_done(c.ocr_job, [[]])
    finals = [j for j in ocr_jobs(jobs) if c_final(c, j)]
    assert finals, "after typing stops a final OCR must come"


def c_final(c, job):
    return c._submitted_final.get(job.id, False)


def test_c1_a_lost_final_ocr_is_requested_again():
    c, jobs, _, _ = make([BLACK])
    c.tick(0)
    first = ocr_jobs(jobs)[-1]
    c.on_job_failed(first.id, "superseded")
    c.tick(300)
    assert len(ocr_jobs(jobs)) == 2


def test_c2_a_block_unchanged_for_1_5_s_is_finished_even_while_the_screen_animates():
    clock = Clock()
    c, jobs, _, overlays = make([BLACK, WHITE] * 40, scope="screen", clock=clock)
    c.ocr_job = 90
    c._ocr_final[90] = False
    c.on_ocr_done(90, [[para("Press the button to continue")]])
    assert translate_jobs(jobs) == []
    clock.now = 1000
    c.ocr_job = 91
    c._ocr_final[91] = False
    c.on_ocr_done(91, [[para("Press the button to continue")]])  # same text, but maybe still fading in
    assert translate_jobs(jobs) == []
    clock.now = 1600
    c.ocr_job = 92
    c._ocr_final[92] = False
    c.on_ocr_done(92, [[para("Press the button to continue")]])  # unchanged for 1.6 s: it has stopped
    assert sources(translate_jobs(jobs)[-1]) == ["Press the button to continue"]


def test_i1_overlays_are_recreated_when_the_window_moves():
    made = []

    def factory(r):
        made.append(r)
        return FakeOverlay()

    win = Window((100, 50, 1000, 500))
    c = LiveController(PARAMS, capture=Script([BLACK]), submit=lambda j: None, next_id=iter(range(1, 99)).__next__,
                       notify=lambda m: None, overlay_factory=factory, use_timer=False)
    c.start_relative([(0, 0, 1, 1)], win)
    c.tick(0)
    win.frame = (2000, 50, 1000, 500)  # dragged to the second monitor
    c.tick(300)
    assert made[-1] == (2000, 50, 1000, 500)


def test_i2_minimizing_the_game_removes_the_translations():
    win = Window((0, 0, 400, 80))
    c, jobs, _, _ = make_rel([BLACK], win, [(0, 0, 1, 1)])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    translate(c, translate_jobs(jobs)[-1])
    overlay = c._overlays[0]
    assert overlay.blocks
    win.frame = None
    c.tick(300)
    assert overlay.blocks == {}


def test_i6_a_misread_last_glyph_keeps_the_block_and_its_translation():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Where are you going? The sta")]])
    translate(c, translate_jobs(jobs)[-1])
    key = next(iter(overlays[0].blocks))
    c.ocr_job = 99
    c._ocr_final[99] = False
    c.on_ocr_done(99, [[para("Where are you going? The sla")]])
    assert list(overlays[0].blocks) == [key] and overlays[0].blocks[key] == "VI Where are you going?"


def test_i6_translations_carry_over_to_a_block_that_got_a_new_key():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello there.")]])
    translate(c, translate_jobs(jobs)[-1])
    n = len(translate_jobs(jobs))
    c.ocr_job = 99
    c._ocr_final[99] = True
    c.on_ocr_done(99, [[para("Hello there.", top=200)]])  # same text, far away: new block
    assert len(translate_jobs(jobs)) == n
    assert list(overlays[0].blocks.values()) == ["VI Hello there."]



def test_ocr_noise_and_ui_labels_are_not_translated():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    noise = Paragraph("text", "St3loo 3,", ["St3loo 3,"], 0, 0, 200, 40, line_height=40)
    label = Paragraph("text", "AUTO", ["AUTO"], 300, 0, 390, 40, line_height=40)
    line = Paragraph("text", "Where are you going?", ["Where are you going?"], 0, 100, 380, 140, line_height=40)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[noise, label, line]])
    assert sources(translate_jobs(jobs)[-1]) == ["Where are you going?"]


def test_a_superseded_translation_is_requested_again_at_once_even_if_the_screen_stays_still():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    lost = translate_jobs(jobs)[-1]
    c.on_job_failed(lost.id, "superseded")
    again = translate_jobs(jobs)[-1]  # no new OCR needed
    assert again.id != lost.id and sources(again) == ["Hello."]
    translate(c, again)
    assert list(overlays[0].blocks.values()) == ["VI Hello."]


def test_a_failed_translation_is_not_retried_in_a_loop():
    c, jobs, _, _ = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    n = len(translate_jobs(jobs))
    c.on_job_failed(translate_jobs(jobs)[-1].id, "model crashed")
    assert len(translate_jobs(jobs)) == n  # a real error waits for the next OCR


def test_a_tilted_block_keeps_its_angle_and_samples_inside_the_image():
    c, jobs, _, overlays = make([_boxed((250, 250, 250), (20, 20, 20))])
    c.tick(0)
    p = Paragraph("text", "Hello there friend.", ["Hello there friend."], 50, 0, 350, 30, line_height=30, angle=-10.0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[p]])
    translate(c, translate_jobs(jobs)[-1])
    key = next(iter(overlays[0].blocks))
    assert overlays[0].angles[key] == -10.0


def test_m4_dragging_the_window_waits_until_it_stops_before_reading():
    win = Window((100, 50, 1000, 500))
    c, jobs, _, _ = make_rel([BLACK], win, [(0, 0, 1, 1)])
    c.tick(0)
    n = len(ocr_jobs(jobs))
    for t in range(100, 800, 100):  # dragged: moves every tick
        win.frame = (100 + t, 50, 1000, 500)
        c.tick(t)
    assert len(ocr_jobs(jobs)) == n  # no OCR while it moves
    for t in range(800, 1400, 100):
        c.tick(t)
    assert len(ocr_jobs(jobs)) == n + 1  # one read once it stood still


def test_m7_a_late_translation_does_not_overwrite_the_users_fix():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    late = translate_jobs(jobs)[-1]
    c.apply_correction("Hello.", "Chào cậu.")
    translate(c, late)  # the machine translation arrives after the fix
    assert list(overlays[0].blocks.values()) == ["Chào cậu."]


def test_m8_a_kept_block_that_moved_is_redrawn_at_its_new_place():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello.")]])
    translate(c, translate_jobs(jobs)[-1])
    draws = overlays[0].draws
    c.ocr_job = 99
    c._ocr_final[99] = True
    c.on_ocr_done(99, [[Paragraph("text", "Hello.", ["Hello."], 8, 6, 308, 26)]])  # same text, 10 px away
    assert overlays[0].draws == draws + 1


def test_a_sentence_translated_before_is_shown_at_once_without_a_new_request():
    """Dialogue that comes back (re-opened, repeated line, scrolled log) reuses the shown translation."""
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello there.")]])
    translate(c, translate_jobs(jobs)[-1])
    c._ocr_final[900] = True
    c.on_ocr_done(900, [[para("Something else.")]])  # the line is gone, another one shows
    translate(c, translate_jobs(jobs)[-1])
    n = len(translate_jobs(jobs))
    c._ocr_final[901] = True
    c.on_ocr_done(901, [[para("Hello there.")]])  # the first line again (a new block)
    assert len(translate_jobs(jobs)) == n  # no new translation job
    assert list(overlays[0].blocks.values()) == ["VI Hello there."]


def test_remembered_translations_follow_the_users_fix_and_reset_on_restart():
    c, jobs, _, overlays = make([BLACK])
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello there.")]])
    translate(c, translate_jobs(jobs)[-1])
    c.apply_correction("Hello there.", "Chào bạn.")
    c._ocr_final[900] = True
    c.on_ocr_done(900, [[]])
    c._ocr_final[901] = True
    c.on_ocr_done(901, [[para("Hello there.")]])
    assert list(overlays[-1].blocks.values()) == ["Chào bạn."]
    c.start([REGION])  # e.g. another model: translate again
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[para("Hello there.")]])
    assert sources(translate_jobs(jobs)[-1]) == ["Hello there."]


# ---- Live review fixes ----------------------------------------------------------------------------------------
class SupersedingWorker:
    """Like TranslationWorker.submit: one waiting live_translate slot, the older one fails "superseded"
    synchronously (Qt calls the slot directly on the UI thread). Nothing is taken: the worker is busy."""

    def __init__(self):
        self.c = None
        self.jobs = []
        self.waiting = None
        self.depth = 0
        self.max_depth = 0

    def submit(self, job):
        self.jobs.append(job)
        if job.mode != "live_translate":
            return
        old, self.waiting = self.waiting, job
        if old is not None:
            self.depth += 1
            self.max_depth = max(self.max_depth, self.depth)
            self.c.on_job_failed(old.id, "superseded")
            self.depth -= 1


def make_superseding():
    w = SupersedingWorker()
    ids = iter(range(1, 10000))
    overlays = []
    c = LiveController(PARAMS, capture=Script([BLACK]), submit=w.submit, next_id=lambda: next(ids), notify=lambda m: None,
                       overlay_factory=lambda r: overlays.append(FakeOverlay()) or overlays[-1], use_timer=False, clock=Clock())
    w.c = c
    c.start([REGION, (600, 500, 400, 80)])
    return c, w, overlays


def test_superseded_translations_do_not_ping_pong_and_nothing_is_lost():  # review #1 (stack overflow)
    c, w, _ = make_superseding()
    c.tick(0)
    first = ocr_jobs(w.jobs)[-1]
    c.on_ocr_done(first.id, [[para("Hello there.")], []])          # job A waits (the worker is busy)
    c._ocr_final[900] = True
    c.on_ocr_done(900, [[para("Hello there."), para("Where to?", top=40)], [para("Good morning.")]])  # B supersedes A
    assert w.max_depth <= 3
    waiting = sources(w.waiting)
    assert sorted(waiting) == ["Good morning.", "Hello there.", "Where to?"]  # the waiting job carries everything


def test_a_resent_job_over_several_regions_draws_each_translation_in_its_own_region():  # review #2
    c, jobs, _, overlays = make([BLACK], regions=(REGION, (600, 500, 400, 80)))
    c.tick(0)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[], [para("Good morning.")]])           # J1: region 1
    j1 = translate_jobs(jobs)[-1]
    c._ocr_final[900] = True
    c.on_ocr_done(900, [[para("Where is the key?")], [para("Good morning.")]])  # J2: region 0 only
    c.on_job_failed(j1.id, "superseded")                                          # J3: both regions
    translate(c, translate_jobs(jobs)[-1])
    assert list(overlays[0].blocks.values()) == ["VI Where is the key?"]
    assert list(overlays[1].blocks.values()) == ["VI Good morning."]


def test_the_last_sentence_appears_on_an_animated_background_with_jittery_reads():  # review #4
    clock = Clock()
    c, jobs, _, overlays = make([BLACK], clock=clock)
    texts = ["We need to go now. The bridge is closing.", "We need to go now. The bridge is cIosing."]
    for n in range(8):  # never a final read: the background never stands still
        clock.now = n * 500
        c._ocr_final[1000 + n] = False
        c.on_ocr_done(1000 + n, [[para(texts[n % 2])]])
        for job in translate_jobs(jobs):
            if job.id in c._requests:
                translate(c, job)
    shown = list(overlays[0].blocks.values())
    assert shown in (["VI We need to go now. VI The bridge is closing."], ["VI We need to go now. VI The bridge is cIosing."])


def test_live_translate_jobs_carry_the_speaker_of_the_dialogue_box():  # review #5
    c, jobs, _, _ = make([BLACK])
    c.tick(0)
    name = Paragraph("name", "Vertin", ["Vertin"], 0, 0, 80, 18)
    c.on_ocr_done(ocr_jobs(jobs)[-1].id, [[name, para("Where are you going?", top=30)]])
    job = translate_jobs(jobs)[-1]
    assert job.payload == {"speaker": "Vertin"}


def test_an_unexpected_error_in_a_tick_does_not_stop_live():  # review minor: the single-shot timer was never re-armed
    c, jobs, notes, _ = make([BLACK])
    scheduled = []
    c._schedule = scheduled.append
    c._on_screen = lambda r: 1 / 0  # anything unexpected while capturing
    try:
        c.tick(0)
    except ZeroDivisionError:
        pass
    assert scheduled  # the next tick is still scheduled
