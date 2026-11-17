"""Append (source, translation) pairs to translations.jsonl — training data for later fine-tuning."""
import json
import threading
from pathlib import Path


class PairLogger:
    def __init__(self, path: Path, enabled: bool):
        self.path = Path(path)
        self.enabled = enabled
        self._lock = threading.Lock()

    def log(self, source: str, translation: str, model_id: str, game: str | None) -> None:
        if not self.enabled:
            return
        row = {"source": source, "translation": translation, "model": model_id, "game": game}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
