"""Characters sent to remote engines today (daily limit against surprise bills)."""
import json
from datetime import date
from pathlib import Path
from typing import Callable


class Usage:
    def __init__(self, data_dir: Path, clock: Callable[[], date] = date.today):
        self.path = Path(data_dir) / "usage.json"
        self._clock = clock

    def _read(self) -> tuple[str, int]:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return str(d["date"]), int(d["chars"])
        except (OSError, ValueError, KeyError, TypeError):
            return "", 0

    def today(self) -> str:
        return self._clock().isoformat()

    def used(self) -> int:
        day, chars = self._read()
        return chars if day == self.today() else 0

    def allows(self, chars: int, limit: int) -> bool:
        return self.used() + chars <= limit

    def add(self, chars: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")  # a crash mid-write must not reset the counter
        tmp.write_text(json.dumps({"date": self.today(), "chars": self.used() + chars}), encoding="utf-8")
        tmp.replace(self.path)
