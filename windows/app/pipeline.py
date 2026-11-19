"""OCR -> postprocess -> cache -> glossary -> translator -> segments."""
import time
from dataclasses import dataclass
from typing import Iterator, Literal

from PIL import Image

from app.cache import TranslationCache, normalize
from app.datalog import CorrectionLogger, PairLogger
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
    angle: float = 0.0  # tilted text: the box is in the frame rotated by -angle (ocr/deskew.py)


@dataclass
class PipelineResult:
    segments: list[Segment]
    timings_ms: dict[str, float]


def collapse_repeats(text: str) -> str:
    """A model stuck in a loop ("may may may may"): a word repeated 3+ times in a row is kept once
    (Vietnamese doubles such as "từ từ" stay)."""
    words = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and words[j + 1].lower() == words[i].lower() and words[i]:
            j += 1
        out.extend(words[i:j + 1] if j - i < 2 else [words[i]])
        i = j + 1
    return " ".join(out)


JUNK_MARKS = "#*_~|"


def clean_output(source: str, text: str) -> str:
    """Strip marks the model invented around a translation ("# Chuyển lên #", "**...**") when the
    source has none of them; then collapse looping words."""
    if not any(c in source for c in JUNK_MARKS):
        text = text.strip().strip(JUNK_MARKS + " ").strip()
    return collapse_repeats(text)


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
        model_version: str = "0",
        overrides: dict[str, str] | None = None,
        corrections: CorrectionLogger | None = None,
    ):
        self.ocr = ocr
        self.translator = translator
        self.glossary = glossary
        self.cache = cache
        self.tracker = tracker
        self.pair_logger = pair_logger
        self.game = game
        self.model_version = model_version
        self.overrides: dict[str, str] = {normalize(k): v for k, v in (overrides or {}).items()}
        self.corrections = corrections

    @property
    def cache_ns(self) -> str:
        """Cache key prefix: a new model version or glossary edit must not reuse old translations."""
        return f"{self.translator.model_id}@{self.model_version}#{self.glossary.digest()}"

    def set_game(self, game: str | None, glossary: Glossary, overrides: dict[str, str]) -> None:
        self.game, self.glossary = game, glossary
        self.overrides = {normalize(k): v for k, v in overrides.items()}

    def correct(self, source: str, machine: str, corrected: str) -> None:
        """The user fixed a translation: use it from now on (before cache and model), and log it."""
        self.overrides[normalize(source)] = corrected
        if self.corrections is not None:
            self.corrections.log(self.game, self.translator.model_id, source, machine, corrected)

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
        ns = self.cache_ns
        done: dict[str, str] = {}
        todo: list[str] = []
        for s in dict.fromkeys(sentences):  # unique, in order
            fixed = self.overrides.get(normalize(s))
            if fixed is not None:  # the user's own translation wins over cache and model
                done[s] = fixed
                continue
            hit = self.cache.get(ns, s)
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
            restored = clean_output(s, restored) if restored is not None else None
            if restored is None:
                retry.append(s)
            else:
                done[s] = restored
        if retry:  # the model damaged a placeholder: translate those without glossary protection
            for s, out in zip(retry, self.translator.translate(retry)):
                done[s] = out
        for s in todo:
            if s not in retry:  # the no-glossary fallback is a degraded result: do not remember it
                self.cache.put(ns, s, done[s])
            if self.pair_logger is not None:
                self.pair_logger.log(s, done[s], model, self.game)
        return done

    def _observe(self, sentences: list[str]) -> None:
        if self.tracker is not None:
            for s in sentences:
                for term in self.tracker.observe(s):
                    self.glossary.add_keep(term)

    @staticmethod
    def _segment(p: Paragraph, translated: dict[str, str]) -> Segment:
        box = (p.left, p.top, p.right, p.bottom)
        if p.kind == "name":
            return Segment("name", p.text, None, box, p.angle)
        return Segment("text", p.text, " ".join(translated[s] for s in p.sentences), box, p.angle)

    def translate_paragraphs(self, paragraphs: list[Paragraph]) -> list[Segment]:
        """One translator batch for every sentence (one-shot region mode)."""
        sentences = [s for p in paragraphs if p.kind == "text" for s in p.sentences]
        self._observe(sentences)
        translated = self._translate_sentences(sentences) if sentences else {}
        return [self._segment(p, translated) for p in paragraphs]

    def iter_sentences(self, paragraphs: list[Paragraph]) -> Iterator[list[Segment]]:
        """Live: after each translated sentence yield all segments; untranslated sentences show "…"."""
        self._observe([s for p in paragraphs if p.kind == "text" for s in p.sentences])
        order = list(dict.fromkeys(s for p in paragraphs if p.kind == "text" for s in p.sentences))
        done: dict[str, str] = {}

        def snapshot() -> list[Segment]:
            out = []
            for p in paragraphs:
                box = (p.left, p.top, p.right, p.bottom)
                if p.kind == "name":
                    out.append(Segment("name", p.text, None, box, p.angle))
                else:
                    out.append(Segment("text", p.text, " ".join(done.get(s, "…") for s in p.sentences), box, p.angle))
            return out

        if not order:
            yield snapshot()
            return
        for sentence in order:
            done.update(self._translate_sentences([sentence]))
            yield snapshot()

    def iter_segments(self, paragraphs: list[Paragraph]) -> Iterator[Segment]:
        """Yield each paragraph as soon as it is translated (full-screen mode shows blocks progressively)."""
        self._observe([s for p in paragraphs if p.kind == "text" for s in p.sentences])
        for p in paragraphs:
            translated = self._translate_sentences(p.sentences) if p.kind == "text" and p.sentences else {}
            yield self._segment(p, translated)
