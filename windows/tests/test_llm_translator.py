"""LlmTranslator: context, glossary, fallback, back-off, limit; and how the Pipeline uses it."""
import json
from datetime import date

from PIL import Image

from app.cache import TranslationCache
from app.glossary import Entry, Glossary
from app.ocr.base import Line
from app.pipeline import Pipeline
from app.translate.llm import LlmTranslator
from app.translate.remote import RemoteError
from app.usage import Usage
from fakes import FakeOcr, FakeTranslator


class FakeClient:
    name = "Gemini"
    model = "gemini-x"

    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error
        self.calls: list[tuple[str, str, float]] = []

    def complete(self, system, user, timeout_s):
        self.calls.append((system, user, timeout_s))
        if self.error is not None:
            raise self.error
        if self.reply is not None:
            return self.reply
        sentences = json.loads(user.rsplit("\n", 1)[1])
        return json.dumps({"translations": [f"LLM {s}" for s in sentences]})


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(tmp_path, client=None, limit=50_000, clock=None):
    notes = []
    local = FakeTranslator(lambda t: f"LOCAL {t}", "vinai")
    tr = LlmTranslator("gemini", client or FakeClient(), local, Usage(tmp_path, clock=lambda: date(2026, 11, 19)),
                       limit, notes.append, clock=clock or Clock())
    return tr, local, notes


def test_model_id_and_batch_preference(tmp_path):
    tr, _, _ = make(tmp_path)
    assert tr.model_id == "gemini:gemini-x" and tr.prefers_batch and tr.local.model_id == "vinai"


def test_translates_with_context_speaker_and_glossary(tmp_path):
    c = FakeClient()
    tr, _, _ = make(tmp_path, c)
    tr.timeout_s = 2.5
    assert tr.translate_ctx(["Hello.", "Bye."], {}) == ["LLM Hello.", "LLM Bye."]
    tr.set_speaker("Vertin")
    tr.translate_ctx(["Druvis III is here."], {"Druvis III": None})
    _, user, timeout = c.calls[-1]
    assert timeout == 2.5
    assert "- Hello.\n- Bye." in user and "Người nói: Vertin" in user and "- Druvis III (giữ nguyên)" in user


def test_failure_falls_back_once_then_waits_30_s_before_trying_again(tmp_path):  # RF3
    clock = Clock()
    c = FakeClient(error=RemoteError("timeout", "Gemini"))
    tr, _, notes = make(tmp_path, c, clock=clock)
    assert tr.translate_ctx(["Hi."], {}) is None  # None: the pipeline translates locally
    assert tr.translate_ctx(["Yo."], {}) is None
    assert len(c.calls) == 1 and len(notes) == 1 and "Gemini" in notes[0] and "model trên máy" in notes[0]
    clock.t += 31
    c.error = None
    assert tr.translate_ctx(["Hi."], {}) == ["LLM Hi."]
    assert len(c.calls) == 2


def test_wrong_key_stops_calling_until_a_new_translator(tmp_path):
    c = FakeClient(error=RemoteError("auth", "Gemini"))
    clock = Clock()
    tr, _, notes = make(tmp_path, c, clock=clock)
    assert tr.translate_ctx(["Hi."], {}) is None
    clock.t += 3600
    assert tr.translate_ctx(["Hi."], {}) is None
    assert len(c.calls) == 1 and "key" in notes[0] and "Cài đặt" in notes[0]


def test_daily_limit_goes_local_with_one_notice(tmp_path):  # RF4
    c = FakeClient()
    tr, _, notes = make(tmp_path, c, limit=10)
    assert tr.translate_ctx(["Hello."], {}) == ["LLM Hello."]  # 6 chars
    assert tr.translate_ctx(["Goodbye."], {}) is None  # 6 + 8 > 10
    assert tr.translate_ctx(["Goodbye."], {}) is None
    assert len(c.calls) == 1 and len(notes) == 1 and "giới hạn" in notes[0]


def test_unusable_reply_goes_local_for_that_batch(tmp_path):  # RF1
    c = FakeClient(reply='{"translations": ["Một."]}')
    tr, _, _ = make(tmp_path, c)
    assert tr.translate_ctx(["One.", "Two."], {}) is None
    c.reply = None
    assert tr.translate_ctx(["One.", "Two."], {}) == ["LLM One.", "LLM Two."]  # no back-off for a bad reply


def test_translate_without_glossary_uses_the_same_rules(tmp_path):
    tr, local, _ = make(tmp_path, FakeClient(error=RemoteError("network", "Gemini")))
    assert tr.translate(["Hi."]) == ["LOCAL Hi."]  # plain Translator protocol: local when remote fails


# ---- Pipeline ------------------------------------------------------------------------------------------
IMG = Image.new("RGB", (10, 10))
LINES = [Line("Vertin", 10, 10, 80, 20), Line("Druvis III waits. We should go. Now.", 10, 60, 600, 24)]


def pipeline(tr, glossary=None):
    return Pipeline(FakeOcr(LINES), tr, glossary or Glossary([Entry("Druvis III", "keep", None, True)]),
                    TranslationCache(100, None))


def test_pipeline_sends_glossary_terms_without_placeholders(tmp_path):
    c = FakeClient()
    tr, _, _ = make(tmp_path, c)
    segs = pipeline(tr).run(IMG).segments
    assert [s.translation for s in segs if s.kind == "text"] == ["LLM Druvis III waits. LLM We should go. LLM Now."]
    _, user, _ = c.calls[0]
    assert "- Druvis III (giữ nguyên)" in user and "[0]" not in user and "Người nói: Vertin" in user


def test_pipeline_live_sentences_use_one_call(tmp_path):
    c = FakeClient()
    tr, _, _ = make(tmp_path, c)
    p = pipeline(tr)
    from app.text.postprocess import postprocess

    snapshots = list(p.iter_sentences(postprocess(LINES)))
    assert len(c.calls) == 1 and len(snapshots) == 3
    assert snapshots[-1][-1].translation == "LLM Druvis III waits. LLM We should go. LLM Now."


def test_pipeline_falls_back_to_the_local_model_and_does_not_cache_it(tmp_path):
    c = FakeClient(error=RemoteError("server", "Gemini"))
    clock = Clock()
    tr, local, _ = make(tmp_path, c, clock=clock)
    p = pipeline(tr)
    segs = p.run(IMG).segments
    assert [s.translation for s in segs if s.kind == "text"][0].startswith("LOCAL ")
    assert local.calls  # the local model translated (with glossary placeholders, as usual)
    clock.t += 31
    c.error = None
    segs = p.run(IMG).segments
    assert [s.translation for s in segs if s.kind == "text"][0].startswith("LLM ")  # not served from cache


# ---- final review fixes ------------------------------------------------------------------------------------
def test_any_client_exception_falls_back_without_showing_its_text(tmp_path):  # review C1
    c = FakeClient(error=RuntimeError("Invalid header value b'Bearer sk-SECRET'"))
    tr, _, notes = make(tmp_path, c)
    assert tr.translate_ctx(["Hi."], {}) is None
    assert len(notes) == 1 and "sk-SECRET" not in notes[0] and "Gemini" in notes[0]


def test_the_timeout_caps_the_whole_call(tmp_path):  # review I2
    import time as _time

    class Slow(FakeClient):
        def complete(self, system, user, timeout_s):
            _time.sleep(1.5)  # a slow DNS / trickling server: per-socket timeouts never fire
            return super().complete(system, user, timeout_s)

    tr, _, notes = make(tmp_path, Slow())
    tr.timeout_s = 0.3
    t0 = _time.monotonic()
    assert tr.translate_ctx(["Hi."], {}) is None
    assert _time.monotonic() - t0 < 1.0 and "quá thời gian" in notes[0]


def test_characters_are_counted_even_when_the_call_fails(tmp_path):  # review I3: a timed-out call may be billed
    tr, _, _ = make(tmp_path, FakeClient(error=RemoteError("timeout", "Gemini")))
    tr.translate_ctx(["Hello."], {})
    assert tr.usage.used() == 6


# ---- 5b-1: per-game context, notes, examples ---------------------------------------------------------------
from app.translate.context_store import ContextStore  # noqa: E402


def make_ctx(tmp_path, client=None, clock=None, today=None):
    notes = []
    local = FakeTranslator(lambda t: f"LOCAL {t}", "vinai")
    day = today or [date(2026, 11, 19)]
    tr = LlmTranslator("gemini", client or FakeClient(), local, Usage(tmp_path, clock=lambda: day[0]), 50_000,
                       notes.append, clock=clock or Clock(), contexts=ContextStore(tmp_path))
    return tr, notes


def test_context_notes_and_examples_are_per_game_and_saved(tmp_path):
    c = FakeClient()
    tr, _ = make_ctx(tmp_path, c)
    tr.set_game("a.exe", "Game A notes.", [("Hi.", "Chào em.")])
    tr.set_speaker("Vertin")
    tr.translate_ctx(["Line A."], {})
    tr.set_game("b.exe", "", [])
    tr.translate_ctx(["Line B."], {})
    user_b = c.calls[-1][1]
    assert "Line A." not in user_b and "Game A notes." not in user_b and "Chào em." not in user_b
    tr2, _ = make_ctx(tmp_path, c)  # a new run (app restarted)
    tr2.set_game("a.exe", "Game A notes.", [("Hi.", "Chào em.")])
    tr2.translate_ctx(["Next."], {})
    user = c.calls[-1][1]
    assert "Về game:\nGame A notes." in user and "- Hi. → Chào em." in user and "- Vertin: Line A." in user


def test_unsafe_game_ids_and_corrupt_files(tmp_path):  # RF1, RF2
    store = ContextStore(tmp_path)
    game = "C:" + chr(92) + "games" + chr(92) + "x?.exe"  # backslashes, colon and ? are not allowed in file names
    store.save(game, [(None, "One.")])
    assert store.load(game) == [(None, "One.")]
    path = next((tmp_path / "llm_context").iterdir())
    path.write_text("{broken", encoding="utf-8")
    assert store.load(game) == []


def test_set_game_clears_a_wrong_key_block_and_back_off(tmp_path):
    c = FakeClient(error=RemoteError("auth", "Gemini"))
    tr, _ = make_ctx(tmp_path, c)
    tr.translate_ctx(["Hi."], {})
    assert not tr.available()
    c.error = None
    tr.set_game("a.exe", "", [])  # settings applied again (e.g. billing fixed on the provider side)
    assert tr.available() and tr.translate_ctx(["Hi."], {}) == ["LLM Hi."]


def test_a_late_result_is_saved_to_the_game_it_was_asked_for(tmp_path):  # RF5
    tr, _ = make_ctx(tmp_path)

    class SwitchMidCall(FakeClient):
        def complete(self, system, user, timeout_s):
            tr.set_game("b.exe", "", [])  # the user switched game while the call was running
            return super().complete(system, user, timeout_s)

    tr.client = SwitchMidCall()
    tr.set_game("a.exe", "", [])
    tr.translate_ctx(["From A."], {})
    store = ContextStore(tmp_path)
    assert store.load("a.exe") == [(None, "From A.")] and store.load("b.exe") == []


def test_the_limit_notice_comes_again_after_midnight(tmp_path):
    day = [date(2026, 11, 19)]
    tr, notes = make_ctx(tmp_path, today=day)
    tr.daily_limit = 3
    tr.translate_ctx(["Hello."], {})
    tr.translate_ctx(["Hello."], {})
    assert len(notes) == 1
    day[0] = date(2026, 11, 20)
    tr.daily_limit = 3
    tr.translate_ctx(["Hello."], {})  # still over the limit on the new day: told again, once
    assert len(notes) == 2


def test_kaggle_servers_get_their_own_cache_namespace():
    from app.translate.remote import make_client

    a = make_client("kaggle", "t", url="https://abc.ngrok-free.app/")
    b = make_client("kaggle", "t", url="https://xyz.ngrok-free.app")
    assert a.model == "abc.ngrok-free.app" and b.model == "xyz.ngrok-free.app"


# ---- 5b-1 Task 4: pipeline fallback stays progressive and cached; fullscreen speaker; corrections ----------
from app.text.postprocess import Paragraph, postprocess  # noqa: E402


def test_live_fallback_still_shows_sentence_by_sentence(tmp_path):
    clock = Clock()
    tr, local, _ = make(tmp_path, FakeClient(error=RemoteError("server", "Gemini")), clock=clock)
    tr.translate_ctx(["warm-up."], {})  # fails: backing off now
    snaps = list(pipeline(tr).iter_sentences(postprocess(LINES)))
    assert len(snaps) == 3 and [len(c) for c in local.calls] == [1, 1, 1]  # one sentence at a time, locally


def test_fallback_results_are_cached_under_the_local_model(tmp_path):
    clock = Clock()
    tr, local, _ = make(tmp_path, FakeClient(error=RemoteError("server", "Gemini")), clock=clock)
    p = pipeline(tr)
    p.run(IMG)
    n = len(local.calls)
    p.run(IMG)  # still backing off: the local translations come from the cache
    assert len(local.calls) == n


def test_fullscreen_sends_a_speaker_only_when_the_screen_has_one_name(tmp_path):
    c = FakeClient()
    tr, _, _ = make(tmp_path, c)
    p = pipeline(tr)
    one = [Paragraph("name", "Vertin", ["Vertin"], 0, 0, 50, 10), Paragraph("text", "Go.", ["Go."], 0, 20, 50, 30)]
    list(p.iter_segments(one))
    assert "Người nói: Vertin" in c.calls[-1][1]
    two = one + [Paragraph("name", "Sonetto", ["Sonetto"], 300, 0, 350, 10),
                 Paragraph("text", "Run.", ["Run."], 300, 20, 350, 30)]
    list(p.iter_segments(two))
    assert "Người nói:" not in c.calls[-1][1]


def test_a_correction_becomes_an_example_for_the_next_call(tmp_path):
    c = FakeClient()
    tr, _, _ = make(tmp_path, c)
    p = pipeline(tr)
    p.correct("You're late.", "Bạn muộn rồi.", "Em đến muộn đấy.")
    p.translate_paragraphs([Paragraph("text", "Hello.", ["Hello."], 0, 0, 50, 10)])
    assert "- You're late. → Em đến muộn đấy." in c.calls[-1][1]


def test_a_locked_usage_file_does_not_fail_the_job(tmp_path, monkeypatch):  # review M4
    c = FakeClient()
    tr, _, _ = make(tmp_path, c)

    def locked(chars):
        raise PermissionError("usage.json is locked")

    monkeypatch.setattr(tr.usage, "add", locked)
    assert tr.translate_ctx(["Hi."], {}) == ["LLM Hi."]
