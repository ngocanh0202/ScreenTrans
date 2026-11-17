"""Translation cache: in-memory LRU, optionally backed by SQLite across runs."""
import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path


def normalize(text: str) -> str:
    return " ".join(text.split())


class TranslationCache:
    def __init__(self, max_items: int, db_path: Path | None):
        self.max_items = max_items
        self._mem: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._lock = threading.Lock()
        self._db = None
        if db_path is not None:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(db_path), check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS translations "
                "(model TEXT, src TEXT, tgt TEXT, PRIMARY KEY (model, src))"
            )
            rows = self._db.execute(
                "SELECT model, src, tgt FROM translations ORDER BY rowid DESC LIMIT ?", (max_items,)
            ).fetchall()
            for model, src, tgt in reversed(rows):
                self._mem[(model, src)] = tgt

    def _remember(self, key: tuple[str, str], value: str) -> None:
        self._mem[key] = value
        self._mem.move_to_end(key)
        while len(self._mem) > self.max_items:
            self._mem.popitem(last=False)

    def get(self, model_id: str, text: str) -> str | None:
        key = (model_id, normalize(text))
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
            if self._db is not None:
                row = self._db.execute(
                    "SELECT tgt FROM translations WHERE model = ? AND src = ?", key
                ).fetchone()
                if row:
                    self._remember(key, row[0])
                    return row[0]
        return None

    def put(self, model_id: str, text: str, translation: str) -> None:
        key = (model_id, normalize(text))
        with self._lock:
            self._remember(key, translation)
            if self._db is not None:
                self._db.execute(
                    "INSERT OR REPLACE INTO translations (model, src, tgt) VALUES (?, ?, ?)", (*key, translation)
                )
                self._db.commit()

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
