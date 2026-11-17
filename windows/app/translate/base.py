"""Translator interface."""
from typing import Protocol

META_FILE = "screentrans_model.json"


class ModelNotFound(Exception):
    pass


class Translator(Protocol):
    model_id: str

    def translate(self, texts: list[str]) -> list[str]:
        """Translate a batch; blank inputs give ""."""
        ...
