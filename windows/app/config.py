"""Load windows/config.yaml over built-in defaults (AGENT.md §12)."""
import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


def _default_data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return str(Path(base) / "ScreenTrans")


@dataclass
class Hotkeys:
    translate_region: str = "ctrl+alt+t"
    translate_fullscreen: str = "ctrl+alt+f"
    toggle_live: str = "ctrl+alt+l"
    edit_last: str = "ctrl+alt+e"


@dataclass
class Ocr:
    engine: str = "windows"


@dataclass
class TranslatorCfg:
    model: str = "vinai-en2vi"
    model_dir: str | None = None
    beam_size: int = 2
    intra_threads: int = 2


@dataclass
class Overlay:
    font_size: int = 14
    opacity: float = 0.85
    show_source: bool = False
    text_scale: float = 1.0   # translation text size factor (settings window)
    long_text: str = "grow"   # Live: "grow" = extend the box downwards first, "shrink" = smaller font only


@dataclass
class Live:
    interval_ms: int = 300
    active_interval_ms: int = 100
    settle_ms: int = 250
    max_wait_ms: int = 2000
    area_min_interval_ms: int = 1000
    area_max_blocks: int = 30
    change_threshold: float = 5
    partial_interval_ms: int = 500  # OCR while the text is typing: show each sentence as soon as it is done


@dataclass
class Cache:
    max_items: int = 5000
    persist: bool = True


@dataclass
class Logging:
    save_pairs: bool = True
    save_corrections: bool = True


@dataclass
class Models:
    manifest_url: str = "https://huggingface.co/anhbui02/screentrans-models/resolve/main/manifest.json"


@dataclass
class Paths:
    data_dir: str = field(default_factory=_default_data_dir)


@dataclass
class Config:
    hotkeys: Hotkeys = field(default_factory=Hotkeys)
    ocr: Ocr = field(default_factory=Ocr)
    translator: TranslatorCfg = field(default_factory=TranslatorCfg)
    overlay: Overlay = field(default_factory=Overlay)
    live: Live = field(default_factory=Live)
    cache: Cache = field(default_factory=Cache)
    logging: Logging = field(default_factory=Logging)
    models: Models = field(default_factory=Models)
    paths: Paths = field(default_factory=Paths)


def _apply(obj, data: dict, where: str) -> None:
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            raise ConfigError(f"Unknown config key '{where}{key}'")
        current = getattr(obj, key)
        if value is None:  # null in YAML = keep the built-in default
            continue
        if is_dataclass(current):
            if not isinstance(value, dict):
                raise ConfigError(f"Config key '{where}{key}' must be a mapping")
            _apply(current, value, f"{where}{key}.")
        else:
            setattr(obj, key, value)


OLD_MANIFEST_URL = "https://github.com/ngocanh0202/ScreenTrans/releases/download/models-v1/manifest.json"


def load_config(path: Path | None) -> Config:
    cfg = Config()
    if path is None or not Path(path).is_file():
        return cfg
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError("Config file must contain a mapping")
    _apply(cfg, data, "")
    if cfg.models.manifest_url == OLD_MANIFEST_URL:  # never published there: the models moved to Hugging Face
        cfg.models.manifest_url = Models().manifest_url
    return cfg
