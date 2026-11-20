"""Which EN-VI sentence pairs are good enough to fine-tune on (Phase 6). Pure functions, tested locally."""
import re

_URL = re.compile(r"https?://|www\.|\S+@\S+\.\w+")
_VI = re.compile("[đĐàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ"
                 "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸ]")
MAX_WORDS = 200


def normalize(s: str) -> str:
    return " ".join(s.replace("﻿", "").split())


def keep_pair(en: str, vi: str) -> bool:
    en, vi = normalize(en), normalize(vi)
    if not en or not vi:
        return False
    we, wv = len(en.split()), len(vi.split())
    if we > MAX_WORDS or wv > MAX_WORDS:
        return False
    if _URL.search(en) or _URL.search(vi):
        return False
    if not re.search(r"[A-Za-z]", en):
        return False  # numbers / symbols only
    ratio = len(vi) / len(en)
    if not (0.5 <= ratio <= (3.0 if len(en) >= 10 else 5.0)):  # short lines ("Hi." -> "Xin chào.") vary more
        return False
    if wv >= 4 and not _VI.search(vi):
        return False  # not Vietnamese (or diacritics stripped)
    if we >= 3 and en.casefold() == vi.casefold():
        return False  # untranslated copy
    return True


def dedupe(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """One pair per source sentence (casefolded, whitespace-normalized), first kept."""
    seen: set[str] = set()
    out = []
    for en, vi in pairs:
        key = normalize(en).casefold()
        if key not in seen:
            seen.add(key)
            out.append((normalize(en), normalize(vi)))
    return out


def split_heldout(pairs: list[tuple[str, str]], heldout_en: set[str]) -> list[tuple[str, str]]:
    """Drop pairs whose source is an evaluation sentence (casefolded): eval never leaks into training."""
    held = {normalize(s).casefold() for s in heldout_en}
    return [(en, vi) for en, vi in pairs if normalize(en).casefold() not in held]
