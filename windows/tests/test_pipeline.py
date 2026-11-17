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
