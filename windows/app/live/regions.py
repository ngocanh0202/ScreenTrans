"""Live regions for Windows (physical pixels), kept in data_dir/live_regions.json until game profiles (4b)."""
import json
from pathlib import Path

FILE = "live_regions.json"


def load_live_regions(data_dir: Path) -> list[tuple[int, int, int, int]]:
    try:
        raw = json.loads((Path(data_dir) / FILE).read_text(encoding="utf-8"))
        return [tuple(int(v) for v in r) for r in raw if len(r) == 4]
    except (OSError, ValueError, TypeError):
        return []


def save_live_regions(data_dir: Path, regions: list[tuple[int, int, int, int]]) -> None:
    path = Path(data_dir) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([list(r) for r in regions]), encoding="utf-8")


MODE_FILE = "live_mode.txt"
SCOPES = ("region", "screen")


def load_live_scope(data_dir: Path) -> str:
    """Live scope: "region" (default; old 4a modes dialogue/area too) or "screen"."""
    try:
        scope = (Path(data_dir) / MODE_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return "region"
    return scope if scope in SCOPES else "region"


def save_live_scope(data_dir: Path, scope: str) -> None:
    path = Path(data_dir) / MODE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scope, encoding="utf-8")
