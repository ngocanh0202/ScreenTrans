"""Picking glossary terms in the correction window (rules: shared/fixtures/terms/README.md)."""

PUNCT = ".,!?;:\"'()[]…“”‘’—-"
CLOSERS = "\"'”’)]"
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "st", "mt", "jr", "sr"}


def tokens(sentence: str) -> list[str]:
    return sentence.split()


def core(token: str) -> str:
    return token.strip(PUNCT)


def span(toks: list[str], start: int, end: int) -> str:
    """Tokens start..end (inclusive) as a term: outer punctuation removed ("Ms." keeps its dot)."""
    text = " ".join(toks[start:end + 1]).lstrip(PUNCT)
    last = core(toks[end]).lower() if toks[start:end + 1] else ""
    stripped = text.rstrip(PUNCT)
    if last in ABBREVIATIONS and text[len(stripped):].startswith("."):
        return stripped + "."
    return stripped


def _ends_run(token: str) -> bool:
    t = token.rstrip(CLOSERS)
    if t.endswith((",", ";", ":", "!", "?", "…")):
        return True
    return t.endswith(".") and core(token).lower() not in ABBREVIATIONS


def _capitalized(token: str) -> bool:
    c = core(token)
    return bool(c) and c[0].isupper() and c != "I"


def suggest_names(sentences: list[str], common: set[str], known: set[str]) -> list[str]:
    """Likely names in the sentences (to keep untranslated), first seen first, without the known ones."""
    known_lower = {k.lower() for k in known}
    out: list[str] = []
    seen: set[str] = set()

    def consider(toks: list[str], run: list[int]) -> None:
        if run and run[0] == 0:  # sentence start: "The", "Where", "Ask" are not part of a name
            while run and core(toks[run[0]]).lower() in common and core(toks[run[0]]).lower() not in ABBREVIATIONS:
                run = run[1:]
        if not run or all(core(toks[i]).lower() in common for i in run):
            return
        name = span(toks, run[0], run[-1])
        key = name.lower()
        if key not in seen and key not in known_lower:
            seen.add(key)
            out.append(name)

    for sentence in sentences:
        toks = tokens(sentence)
        run: list[int] = []
        for i, tok in enumerate(toks):
            if _capitalized(tok):
                run.append(i)
                if _ends_run(tok):
                    consider(toks, run)
                    run = []
            else:
                consider(toks, run)
                run = []
        consider(toks, run)
    return out
