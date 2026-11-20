"""Editing a game's own glossary in Settings (rules: shared/fixtures/term_edit; Kotlin TermEdit.kt passes the same
files). A row is (source, target, case_sensitive); target None = keep the source as is."""
import json

Row = tuple[str, str | None, bool]


def parse(text: str) -> list[Row] | None:
    """The rows of a glossary file; None when the file is broken (not an object with an "entries" list)."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return None
    rows: list[Row] = []
    for e in data["entries"]:
        if not isinstance(e, dict) or not isinstance(e.get("source"), str):
            continue
        target = e.get("target") if e.get("type") == "map" and isinstance(e.get("target"), str) else None
        cs = e.get("case_sensitive")
        rows.append((e["source"], target, cs if isinstance(cs, bool) else True))
    return rows


def clean(rows: list[Row]) -> list[Row]:
    """Before saving: trimmed, empty sources dropped, empty targets = keep; a later duplicate source (any case)
    replaces the earlier one in its place."""
    out: list[Row] = []
    where: dict[str, int] = {}
    for source, target, cs in rows:
        source = " ".join(source.split())
        if not source:
            continue
        target = (target or "").strip() or None
        key = source.casefold()
        if key in where:
            out[where[key]] = (source, target, cs)
        else:
            where[key] = len(out)
            out.append((source, target, cs))
    return out


def dump(rows: list[Row]) -> dict:
    entries = []
    for source, target, cs in rows:
        e: dict = {"source": source, "type": "map" if target else "keep"}
        if target:
            e["target"] = target
        e["case_sensitive"] = cs
        entries.append(e)
    return {"entries": entries}
