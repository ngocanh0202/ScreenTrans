"""Per-game profiles (spec §5.5, AGENT.md §10): one JSON file per game in data_dir/profiles.

Reading rules are specified by shared/fixtures/profiles (the Kotlin port passes the same files).
Regions are relative (0-1) to the game window's client area (Windows) / the screen (Android).
"""
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

Rel = tuple[float, float, float, float]
SCOPES = ("region", "screen")
STYLES = ("match", "classic")  # Live colours: sampled from the game / white on dark (font size always matches)
DEFAULT_ID = "_default"


def _norm(text: str) -> str:
    return " ".join(text.split())


def _num(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _rel(v) -> Rel | None:
    if not isinstance(v, list) or len(v) != 4:
        return None
    nums = [_num(x) for x in v]
    if any(n is None for n in nums):
        return None
    x, y, w, h = nums
    x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
    w, h = min(max(w, 0.0), 1.0 - x), min(max(h, 0.0), 1.0 - y)
    if w <= 0 or h <= 0:
        return None
    return (round(x, 6), round(y, 6), round(w, 6), round(h, 6))


def _rels(v) -> list[Rel]:
    return [r for r in (_rel(x) for x in v) if r is not None] if isinstance(v, list) else []


def _positive(v, default, kind=float):
    n = _num(v)
    if n is None or n <= 0 or (kind is int and n != int(n)):
        return default
    return kind(n)


@dataclass
class Profile:
    id: str
    name: str = ""
    scope: str = "region"
    style: str = "match"
    ocr: str = "auto"  # OCR engine for this game: "auto" = the platform default (Windows: windows | rapid)
    regions: list[Rel] = field(default_factory=list)
    ignore: list[Rel] = field(default_factory=list)
    interval_ms: int = 300
    settle_ms: int = 250
    change_threshold: float = 5.0
    glossary: str | None = None
    overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> "Profile | None":
        try:
            d = json.loads(text)
        except ValueError:
            return None
        return cls.from_json(d)

    @classmethod
    def from_json(cls, d) -> "Profile | None":
        if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"]:
            return None
        live = d.get("live") if isinstance(d.get("live"), dict) else {}
        overrides = d.get("overrides") if isinstance(d.get("overrides"), dict) else {}
        return cls(
            id=d["id"],
            name=d["name"] if isinstance(d.get("name"), str) else "",
            ocr=d["ocr"] if isinstance(d.get("ocr"), str) and d["ocr"] else "auto",
            scope=live.get("scope") if live.get("scope") in SCOPES else "region",
            style=live.get("style") if live.get("style") in STYLES else "match",
            regions=_rels(d.get("regions")),
            ignore=_rels(d.get("ignore_regions")),
            interval_ms=_positive(live.get("interval_ms"), 300, int),
            settle_ms=_positive(live.get("settle_ms"), 250, int),
            change_threshold=_positive(live.get("change_threshold"), 5.0),
            glossary=d["glossary"] if isinstance(d.get("glossary"), str) else None,
            overrides={_norm(k): v for k, v in overrides.items() if isinstance(k, str) and _norm(k)
                       and isinstance(v, str)},
        )

    def to_json(self) -> dict:
        return {
            "id": self.id, "name": self.name, "ocr": self.ocr,
            "live": {"scope": self.scope, "style": self.style, "interval_ms": self.interval_ms, "settle_ms": self.settle_ms,
                     "change_threshold": self.change_threshold},
            "regions": [list(r) for r in self.regions], "ignore_regions": [list(r) for r in self.ignore],
            "glossary": self.glossary, "overrides": dict(self.overrides),
        }


def to_px(rel: Rel, frame: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    fx, fy, fw, fh = frame
    x, y, w, h = rel
    return round(fx + x * fw), round(fy + y * fh), round(w * fw), round(h * fh)


def to_rel(px: tuple[int, int, int, int], frame: tuple[int, int, int, int]) -> Rel:
    fx, fy, fw, fh = frame
    x, y, w, h = px
    return (round((x - fx) / fw, 6), round((y - fy) / fh, 6), round(w / fw, 6), round(h / fh, 6))


class ProfileStore:
    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def _path(self, game_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in game_id)
        return self.dir / f"{safe}.json"

    def get(self, game_id: str) -> Profile | None:
        path = self._path(game_id)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = None  # saved by another editor in another encoding: treat as broken
        except OSError:
            return None
        p = Profile.parse(text) if text is not None else None
        if p is None:  # keep the broken file for the user, start over with defaults
            try:
                os.replace(path, path.with_name(path.name + ".bad"))
            except OSError:
                pass
        return p

    def get_or_default(self, game_id: str, name: str = "") -> Profile:
        return self.get(game_id) or Profile(game_id, name)

    def save(self, profile: Profile) -> None:
        path = self._path(profile.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(profile.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    def migrate_phase4a(self, data_dir: Path, screen: tuple[int, int, int, int]) -> None:
        """4a kept one Live region (physical px) + a mode file: move them into the `_default` profile."""
        from app.live.regions import FILE, MODE_FILE, load_live_regions, load_live_scope

        data_dir = Path(data_dir)
        old = data_dir / FILE
        if not old.exists():
            return
        if self.get(DEFAULT_ID) is None:
            p = Profile(DEFAULT_ID, "Mặc định", scope=load_live_scope(data_dir),
                        regions=[r for r in (_rel(list(to_rel(px, screen))) for px in load_live_regions(data_dir)) if r])
            self.save(p)
        os.replace(old, old.with_name(old.name + ".migrated"))
        mode = data_dir / MODE_FILE
        if mode.exists():
            os.replace(mode, mode.with_name(mode.name + ".migrated"))
