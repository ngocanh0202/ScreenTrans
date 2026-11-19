"""The last lines of each game's dialogue, for LLM context (Phase 5b): data_dir/llm_context/<game>.json."""
import hashlib
import json
import re
from pathlib import Path

from app.translate.llm_prompt import CONTEXT_MAX

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ContextStore:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "llm_context"

    def _path(self, game: str) -> Path:
        safe = _UNSAFE.sub("_", game).strip("._")[:60] or "game"
        digest = hashlib.sha1(game.encode("utf-8")).hexdigest()[:8]  # distinct ids that sanitize alike stay apart
        return self.dir / f"{safe}-{digest}.json"

    def load(self, game: str) -> list[tuple[str | None, str]]:
        try:
            data = json.loads(self._path(game).read_text(encoding="utf-8"))
            return [(sp if isinstance(sp, str) else None, text) for sp, text in data
                    if isinstance(text, str)][-CONTEXT_MAX:]
        except (OSError, ValueError, TypeError):
            return []

    def save(self, game: str, lines: list[tuple[str | None, str]]) -> None:
        path = self._path(game)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps([list(x) for x in lines[-CONTEXT_MAX:]], ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # context is a nicety: never fail a translation over it
