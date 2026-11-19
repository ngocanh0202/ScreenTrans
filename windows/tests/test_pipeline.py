from pathlib import Path

from PIL import Image

from app.cache import TranslationCache
from app.glossary import PLACEHOLDER, Glossary, ProperNounTracker
from app.ocr.base import Line
from app.pipeline import Pipeline
from fakes import FakeOcr, FakeTranslator

SHARED = Path(__file__).parents[2] / "shared" / "glossary"
IMG = Image.new("RGB", (10, 10))

DIALOGUE = [
    Line("Druvis Ill", 37, 13, 149, 29),
    Line("His worry was washed away. He ran out quickly", 26, 78, 900, 31),
    Line("and left the hat.", 25, 118, 400, 30),
]


def _pipeline(lines, translator, glossary=None, tracker=None):
    return Pipeline(FakeOcr(lines), translator, glossary or Glossary([]), TranslationCache(100, None), tracker=tracker)


def test_name_is_not_translated_and_one_batch():
    tr = FakeTranslator(lambda s: "VI:" + s)
    result = _pipeline(DIALOGUE, tr).run(IMG)
    assert [(s.kind, s.source) for s in result.segments][0] == ("name", "Druvis III")
    assert result.segments[0].translation is None
    assert result.segments[1].translation == "VI:His worry was washed away. VI:He ran out quickly and left the hat."
    assert len(tr.calls) == 1 and len(tr.calls[0]) == 2


def test_two_paragraphs_three_sentences_single_batch():
    lines = [Line("One. Two.", 20, 10, 200, 30), Line("Three.", 20, 200, 100, 30)]
    tr = FakeTranslator(str.upper)
    _pipeline(lines, tr).run(IMG)
    assert tr.calls == [["One.", "Two.", "Three."]]


def test_second_run_hits_cache():
    tr = FakeTranslator(lambda s: "VI:" + s)
    p = _pipeline(DIALOGUE, tr)
    p.run(IMG)
    p.run(IMG)
    assert len(tr.calls) == 1


def test_broken_placeholder_falls_back_to_plain_translation():
    g = Glossary.load(SHARED / "games" / "reverse1999.json")
    tr = FakeTranslator(lambda s: s.replace(PLACEHOLDER.format(i=0), "") + " (vi)")
    result = _pipeline([Line("Hello Vertin.", 20, 10, 200, 30)], tr, glossary=g).run(IMG)
    assert result.segments[0].translation == "Hello Vertin. (vi)"
    assert len(tr.calls) == 2 and tr.calls[1] == ["Hello Vertin."]


def test_glossary_terms_survive():
    g = Glossary.load(SHARED / "games" / "reverse1999.json")
    tr = FakeTranslator(lambda s: s.replace("Good morning", "Chào buổi sáng"))
    result = _pipeline([Line("Good morning, Timekeeper.", 20, 10, 300, 30)], tr, glossary=g).run(IMG)
    assert result.segments[0].translation == "Chào buổi sáng, Timekeeper."


def test_tracker_adds_proper_noun_to_glossary():
    g = Glossary([])
    tracker = ProperNounTracker(set(), min_count=3)
    tr = FakeTranslator(lambda s: s)
    p = _pipeline([], tr, glossary=g, tracker=tracker)
    for i in range(3):
        p.ocr = FakeOcr([Line(f"Hello Sonetto number{i}.", 20, 10, 300, 30)])
        p.run(IMG)
    assert g.protect("Hi Sonetto.")[1] == ["Sonetto"]


def test_timings_and_empty_image():
    result = _pipeline([], FakeTranslator(str.upper)).run(IMG)
    assert result.segments == []
    assert set(result.timings_ms) == {"ocr", "postprocess", "translate", "total"}


def test_degraded_retry_output_is_not_cached():
    g = Glossary.load(SHARED / "games" / "reverse1999.json")
    tr = FakeTranslator(lambda s: s.replace(PLACEHOLDER.format(i=0), "") + " (vi)")
    p = _pipeline([Line("Hello Vertin.", 20, 10, 200, 30)], tr, glossary=g)
    p.run(IMG)
    p.run(IMG)
    assert len(tr.calls) == 4  # translated again: the no-glossary fallback is not remembered


def test_iter_segments_translates_paragraph_by_paragraph():
    from app.text.postprocess import Paragraph

    paras = [
        Paragraph("name", "Druvis III", [], 0, 0, 10, 10),
        Paragraph("text", "One. Two.", ["One.", "Two."], 0, 20, 10, 30),
        Paragraph("text", "Three.", ["Three."], 0, 40, 10, 50),
    ]
    tr = FakeTranslator(str.upper)
    it = _pipeline([], tr).iter_segments(paras)
    first = next(it)
    assert (first.kind, first.translation) == ("name", None) and tr.calls == []
    second = next(it)
    assert second.translation == "ONE. TWO." and tr.calls == [["One.", "Two."]]
    third = next(it)
    assert third.translation == "THREE." and tr.calls == [["One.", "Two."], ["Three."]]
    assert list(it) == []


def test_iter_segments_uses_cache():
    from app.text.postprocess import Paragraph

    tr = FakeTranslator(str.upper)
    p = _pipeline([], tr)
    paras = [Paragraph("text", "Hi.", ["Hi."], 0, 0, 1, 1)]
    list(p.iter_segments(paras))
    list(p.iter_segments(paras))
    assert tr.calls == [["Hi."]]


# ---- 4b: user overrides, versioned cache key, corrections log ---------------------------------------
def _p(tr, overrides=None, glossary=None, cache=None, **kw):
    from app.cache import TranslationCache as C

    return Pipeline(FakeOcr([]), tr, glossary or Glossary([]), cache or C(100, None), overrides=overrides, **kw)


def test_override_wins_over_cache_and_model_whatever_the_whitespace():
    tr = FakeTranslator(lambda s: "VI " + s)
    cache = TranslationCache(100, None)
    p = _p(tr, overrides={"Hello there.": "Chào cậu."}, cache=cache)
    cache.put(p.cache_ns, "Hello  there.", "cached")
    assert p._translate_sentences(["Hello  there."]) == {"Hello  there.": "Chào cậu."}
    assert tr.calls == []


def test_correct_is_used_next_time_and_logged(tmp_path):
    import json

    from app.datalog import CorrectionLogger

    tr = FakeTranslator(lambda s: "VI " + s)
    p = _p(tr, corrections=CorrectionLogger(tmp_path / "corrections.jsonl", True), game="game.exe")
    assert p._translate_sentences(["Run."]) == {"Run.": "VI Run."}
    p.correct("Run.", "VI Run.", "Chạy đi!")
    assert p._translate_sentences(["Run."]) == {"Run.": "Chạy đi!"}
    assert p.overrides == {"Run.": "Chạy đi!"}
    row = json.loads((tmp_path / "corrections.jsonl").read_text(encoding="utf-8"))
    assert set(row) == {"ts", "game", "model", "source", "machine", "corrected"}
    assert (row["game"], row["model"], row["corrected"]) == ("game.exe", "fake", "Chạy đi!")


def test_corrections_log_can_be_turned_off(tmp_path):
    from app.datalog import CorrectionLogger

    p = _p(FakeTranslator(str.upper), corrections=CorrectionLogger(tmp_path / "c.jsonl", False))
    p.correct("a.", "A.", "b.")
    assert not (tmp_path / "c.jsonl").exists() and p.overrides == {"a.": "b."}


def test_cache_namespace_changes_with_glossary_and_model_version_not_with_auto_keep():
    g = Glossary([])
    p = _p(FakeTranslator(str.upper), glossary=g, model_version="2")
    ns = p.cache_ns
    assert ns.startswith("fake@2#")
    g.add_keep("Vertin")  # session tracker term: same namespace
    assert p.cache_ns == ns
    g.add_entry("Arcanist", None)  # user term: old cached translations no longer apply
    assert p.cache_ns != ns


def test_set_game_switches_glossary_and_overrides():
    p = _p(FakeTranslator(lambda s: "VI " + s), overrides={"A.": "a"})
    p.set_game("other.exe", Glossary([]), {"B.": "b"})
    assert p.game == "other.exe" and p._translate_sentences(["A.", "B."]) == {"A.": "VI A.", "B.": "b"}



def test_a_looping_translation_is_collapsed():
    from app.pipeline import collapse_repeats

    assert collapse_repeats("Sự may may may may may may may may may may ...") == "Sự may ..."
    assert collapse_repeats("Từ từ dần dần thôi.") == "Từ từ dần dần thôi."  # Vietnamese doubles stay
    tr = FakeTranslator(lambda s: "Sự may may may may may")
    assert _p(tr)._translate_sentences(["Stealio."]) == {"Stealio.": "Sự may"}
