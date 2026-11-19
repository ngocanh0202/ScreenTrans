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
