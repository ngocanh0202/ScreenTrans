"""OCR -> postprocess -> cache -> glossary -> translator -> segments."""
import time
from dataclasses import dataclass
from typing import Literal

from PIL import Image

from app.cache import TranslationCache
from app.datalog import PairLogger
from app.glossary import Glossary, ProperNounTracker
from app.ocr.base import OcrEngine
from app.text.postprocess import Paragraph, postprocess
from app.translate.base import Translator


@dataclass
class Segment:
    kind: Literal["name", "text"]
    source: str
    translation: str | None
    box: tuple[float, float, float, float]  # left, top, right, bottom


@dataclass
class PipelineResult:
    segments: list[Segment]
    timings_ms: dict[str, float]


class Pipeline:
    """Use one instance from a single worker thread (glossary/tracker/cache state is not locked)."""

    def __init__(
        self,
        ocr: OcrEngine,
        translator: Translator,
        glossary: Glossary,
        cache: TranslationCache,
        tracker: ProperNounTracker | None = None,
        pair_logger: PairLogger | None = None,
        game: str | None = None,
    ):
        self.ocr = ocr
        self.translator = translator
        self.glossary = glossary
        self.cache = cache
        self.tracker = tracker
        self.pair_logger = pair_logger
        self.game = game

    def run(self, img: Image.Image) -> PipelineResult:
        t0 = time.perf_counter()
        lines = self.ocr.recognize(img)
        t1 = time.perf_counter()
        paragraphs = postprocess(lines)
        t2 = time.perf_counter()
        segments = self.translate_paragraphs(paragraphs)
        t3 = time.perf_counter()
        ms = lambda a, b: (b - a) * 1000  # noqa: E731
        return PipelineResult(
            segments,
            {"ocr": ms(t0, t1), "postprocess": ms(t1, t2), "translate": ms(t2, t3), "total": ms(t0, t3)},
        )

    def _translate_sentences(self, sentences: list[str]) -> dict[str, str]:
        model = self.translator.model_id
        done: dict[str, str] = {}
        todo: list[str] = []
        for s in dict.fromkeys(sentences):  # unique, in order
            hit = self.cache.get(model, s)
            if hit is not None:
                done[s] = hit
            else:
                todo.append(s)
        if not todo:
            return done
        protected = [self.glossary.protect(s) for s in todo]
        outputs = self.translator.translate([p for p, _ in protected])
        retry: list[str] = []
        for s, (_, values), out in zip(todo, protected, outputs):
            restored = self.glossary.restore(out, values) if values else out
            if restored is None:
                retry.append(s)
            else:
                done[s] = restored
        if retry:  # the model damaged a placeholder: translate those without glossary protection
            for s, out in zip(retry, self.translator.translate(retry)):
                done[s] = out
        for s in todo:
            if s not in retry:  # the no-glossary fallback is a degraded result: do not remember it
                self.cache.put(model, s, done[s])
            if self.pair_logger is not None:
                self.pair_logger.log(s, done[s], model, self.game)
        return done

    def translate_paragraphs(self, paragraphs: list[Paragraph]) -> list[Segment]:
        sentences = [s for p in paragraphs if p.kind == "text" for s in p.sentences]
        if self.tracker is not None:
            for s in sentences:
                for term in self.tracker.observe(s):
                    self.glossary.add_keep(term)
        translated = self._translate_sentences(sentences) if sentences else {}
        segments = []
        for p in paragraphs:
            box = (p.left, p.top, p.right, p.bottom)
            if p.kind == "name":
                segments.append(Segment("name", p.text, None, box))
            else:
                segments.append(Segment("text", p.text, " ".join(translated[s] for s in p.sentences), box))
        return segments
