"""OCR lines -> paragraphs (name / text) -> sentences.

The rules are specified in shared/fixtures/postprocess/README.md; this module is the
reference implementation the Kotlin port must match on the same fixtures.
"""
import re
import statistics
from dataclasses import dataclass, field
from typing import Literal

from app.ocr.base import Line

JOIN_GAP = 0.8      # max vertical gap (in line heights) between lines of one paragraph
OVERLAP = 0.5       # lines may overlap vertically by this much and still join
NAME_GAP = 2.0      # a name sits at most this far above the text it labels
SAME_ROW = 0.5      # paragraphs whose tops differ less than this are on one row

_JUNK_BRACKETS = set("()[]{}<>|©®")
_END_PUNCT = tuple(".!?,;…\"'”’")
_NAME_TOKEN = re.compile(r"^(?:[A-Z]|[IVXLl1|]{1,4}$)")
_ROMAN_MISREAD = re.compile(r"^[Il1|]{2,4}$")
_NO_SPLIT = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "etc."}
_SENT_END = re.compile(r"[.!?…]+[\"”’']*")


@dataclass
class Paragraph:
    kind: Literal["name", "text"]
    text: str
    sentences: list[str]
    left: float
    top: float
    right: float
    bottom: float


@dataclass
class _Group:
    lines: list[Line] = field(default_factory=list)

    @property
    def left(self) -> float:
        return min(l.left for l in self.lines)

    @property
    def right(self) -> float:
        return max(l.right for l in self.lines)

    @property
    def top(self) -> float:
        return min(l.top for l in self.lines)

    @property
    def bottom(self) -> float:
        return max(l.bottom for l in self.lines)


def _has_letter(s: str) -> bool:
    return any(c.isalpha() for c in s)


def _clean(text: str) -> str:
    tokens = text.split()
    while tokens and (not any(c.isalnum() for c in tokens[0])
                      or (len(tokens[0]) <= 2 and any(c in _JUNK_BRACKETS for c in tokens[0]))):
        tokens.pop(0)
    while tokens and not any(c.isalnum() for c in tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def _join(lines: list[Line]) -> str:
    out = ""
    for line in lines:
        t = " ".join(line.text.split())
        if not out:
            out = t
        elif re.search(r"[a-z]-$", out) and t[:1].islower():
            out = out[:-1] + t
        else:
            out = out + " " + t
    return out


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    out, start = [], 0
    for m in _SENT_END.finditer(text):
        end = m.end()
        rest = text[end:]
        if not (rest.startswith(" ") and len(rest) > 1 and (rest[1].isupper() or rest[1] in "\"“")):
            continue
        token = text[:end].split(" ")[-1].lstrip("\"“‘'(")  # opening quotes don't hide "Mr."
        if token.lower() in _NO_SPLIT or re.fullmatch(r"[A-Z]\.", token):
            continue
        out.append(text[start:end].strip())
        start = end + 1
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _is_name(g: _Group, text: str, groups: list[_Group], h: float) -> bool:
    tokens = text.rstrip(":").split()
    if len(g.lines) != 1 or not 1 <= len(tokens) <= 3:
        return False
    if not all(_NAME_TOKEN.match(t) for t in tokens):
        return False
    if text.endswith(":"):
        return True
    if text.endswith(_END_PUNCT):
        return False
    return any(
        o is not g and 0 <= o.top - g.bottom <= NAME_GAP * h and o.left < g.right + h and o.right > g.left - h
        for o in groups
    )


def _name_text(text: str) -> str:
    tokens = text.rstrip(":").split()
    return " ".join("I" * len(t) if _ROMAN_MISREAD.match(t) else t for t in tokens)


def postprocess(lines: list[Line]) -> list[Paragraph]:
    cleaned = []
    for line in lines:
        t = _clean(line.text)
        if _has_letter(t) and len(t) > 1:
            cleaned.append(Line(t, line.left, line.top, line.width, line.height))
    if not cleaned:
        return []
    h = statistics.median(l.height for l in cleaned)

    groups: list[_Group] = []
    for line in sorted(cleaned, key=lambda l: (l.top, l.left)):
        fits = [g for g in groups
                if -OVERLAP * h <= line.top - g.bottom <= JOIN_GAP * h and g.left - h <= line.left <= g.right]
        if fits:
            max(fits, key=lambda g: g.bottom).lines.append(line)
        else:
            groups.append(_Group([line]))

    groups.sort(key=lambda g: g.top)
    i = 1
    while i < len(groups):  # adjacent paragraphs on the same row: left first
        a, b = groups[i - 1], groups[i]
        if abs(a.top - b.top) < SAME_ROW * h and b.left < a.left:
            groups[i - 1], groups[i] = b, a
            i = max(1, i - 1)
        else:
            i += 1

    out = []
    for g in groups:
        text = _join(g.lines)
        if _is_name(g, text, groups, h):
            out.append(Paragraph("name", _name_text(text), [], g.left, g.top, g.right, g.bottom))
        else:
            out.append(Paragraph("text", text, split_sentences(text), g.left, g.top, g.right, g.bottom))
    return out
