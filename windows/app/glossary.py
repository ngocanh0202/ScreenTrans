"""Glossary: keep/map terms protected by placeholders around the translator (AGENT.md §9)."""
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.paths import shared_dir

COMMON_GLOSSARY = shared_dir() / "glossary" / "common.json"
COMMON_WORDS = shared_dir() / "glossary" / "common_words_en.txt"


def games_dir() -> Path:
    return shared_dir() / "glossary" / "games"

# Chosen in Task 4 Step 5 by measuring survival through the translator.
PLACEHOLDER = "[{i}]"  # survived 10/10 through vinai, 7/10 opus; "⟦{i}⟧" 0/10


def _placeholder_any() -> re.Pattern:
    return re.compile(re.escape(PLACEHOLDER).replace(r"\{i\}", r"(\d+)"))


@dataclass(frozen=True)
class Entry:
    source: str
    kind: str  # "keep" | "map"
    target: str | None
    case_sensitive: bool

    @property
    def value(self) -> str | None:
        return self.target if self.kind == "map" else None


class Glossary:
    """Not thread-safe: the app uses one Pipeline (and its glossary) from a single worker thread."""

    AUTO_PRIORITY = 1_000_000  # tracker terms rank below every loaded entry

    def __init__(self, entries: list[Entry]):
        # value: (priority, entry); a lower priority number wins, across exact and folded maps
        self._exact: dict[str, tuple[int, Entry]] = {}
        self._folded: dict[str, tuple[int, Entry]] = {}
        self._user: list[Entry] = list(entries)  # loaded + user-added entries (not tracker terms): the digest
        self._next_user_priority = -1
        for prio, e in enumerate(entries):  # earlier entries have priority
            if e.case_sensitive:
                self._exact.setdefault(e.source, (prio, e))
            else:
                self._folded.setdefault(e.source.lower(), (prio, e))
        self._compile()

    @classmethod
    def load(cls, *paths: Path) -> "Glossary":
        entries = []
        for p in paths:
            for raw in json.loads(Path(p).read_text(encoding="utf-8"))["entries"]:
                entries.append(Entry(raw["source"], raw["type"], raw.get("target"), raw.get("case_sensitive", True)))
        return cls(entries)

    def _compile(self) -> None:
        sources = sorted({*self._exact, *(e.source for _, e in self._folded.values())}, key=len, reverse=True)
        self._pattern = (
            re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, sources)) + r")(?!\w)", re.IGNORECASE)
            if sources else None
        )

    def add_keep(self, term: str) -> None:
        """Add a tracker term unless the glossary already knows it (in any case)."""
        if term in self._exact or term.lower() in self._folded:
            return
        self._exact[term] = (self.AUTO_PRIORITY, Entry(term, "keep", None, True))
        self._compile()

    def add_entry(self, source: str, target: str | None) -> None:
        """A term the user added while correcting: `keep` (target None/empty) or `map`; wins over every entry."""
        source = source.strip()
        if not source:
            return
        e = Entry(source, "map" if target else "keep", target or None, True)
        self._exact[source] = (self._next_user_priority, e)
        self._next_user_priority -= 1
        self._user.append(e)
        self._compile()

    def digest(self) -> str:
        """12-hex fingerprint of the loaded/user entries; part of the cache key so edits invalidate it."""
        import hashlib

        rows = sorted(json.dumps([e.source, e.kind, e.target, e.case_sensitive], ensure_ascii=False) for e in self._user)
        return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()[:12]

    def _lookup(self, matched: str) -> Entry | None:
        candidates = [c for c in (self._exact.get(matched), self._folded.get(matched.lower())) if c]
        return min(candidates, key=lambda c: c[0])[1] if candidates else None

    def terms_in(self, texts: list[str]) -> dict[str, str | None]:
        """Entries that occur in `texts` (same matching as protect): source -> target, None = keep as is."""
        found: dict[str, str | None] = {}
        if self._pattern is None:
            return found
        for text in texts:
            for m in self._pattern.finditer(text):
                entry = self._lookup(m.group(0))
                if entry is not None:
                    found.setdefault(entry.source, entry.value)
        return found

    def protect(self, text: str) -> tuple[str, list[str]]:
        if self._pattern is None:
            return text, []
        values: list[str] = []

        def repl(m: re.Match) -> str:
            entry = self._lookup(m.group(0))
            if entry is None:  # case-sensitive entry matched with the wrong case
                return m.group(0)
            values.append(entry.value or m.group(0))
            return PLACEHOLDER.format(i=len(values) - 1)

        return self._pattern.sub(repl, text), values

    @staticmethod
    def restore(text: str, values: list[str]) -> str | None:
        found = [int(n) for n in _placeholder_any().findall(text)]
        if sorted(found) != list(range(len(values))):
            return None
        return _placeholder_any().sub(lambda m: values[int(m.group(1))], text)


def load_common_words(path: Path = COMMON_WORDS) -> set[str]:
    return {w.strip().lower() for w in path.read_text(encoding="utf-8").splitlines() if w.strip()}


class ProperNounTracker:
    """Capitalized, non-sentence-initial, uncommon words seen min_count times become keep terms."""

    _WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")

    def __init__(self, common_words: set[str], min_count: int = 3):
        self.common_words = common_words
        self.min_count = min_count
        self._counts: Counter[str] = Counter()
        self._reported: set[str] = set()
        self._seen: set[str] = set()

    def observe(self, sentence: str) -> list[str]:
        """Count each distinct sentence once (re-OCR of the same screen must not promote words)."""
        key = " ".join(sentence.split())
        if key in self._seen:
            return []
        self._seen.add(key)
        new = []
        for word in self._WORD.findall(sentence)[1:]:
            if not word[0].isupper() or word.lower() in self.common_words:
                continue
            self._counts[word] += 1
            if self._counts[word] >= self.min_count and word not in self._reported:
                self._reported.add(word)
                new.append(word)
        return new
