"""Where bundled resources live: the repo when run from source, sys._MEIPASS when packaged."""
import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def shared_dir() -> Path:
    return resource_root() / "shared"


def default_config_path() -> Path:
    return resource_root() / "windows" / "config.yaml"
