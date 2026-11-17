"""Download translation models listed in the public manifest.json, verified by SHA-256."""
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from app.translate.base import ModelNotFound

CHUNK = 1 << 20
COMPLETE = ".complete"  # written once every file of a model version is downloaded and verified


class ModelDownloadError(Exception):
    pass


def _fetch_manifest(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ModelDownloadError(
            f"Cannot read the model manifest at {url} ({e}). Check the network, or pass --model-dir "
            f"with a locally exported model."
        ) from e


def _download(url: str, dest: Path, sha256: str, on_bytes: Callable[[int], None]) -> None:
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as r, part.open("wb") as f:
            while chunk := r.read(CHUNK):
                f.write(chunk)
                digest.update(chunk)
                on_bytes(len(chunk))
    except (urllib.error.URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"Download of {dest.name} failed ({e}). Try again, or pass --model-dir with a local model."
        ) from e
    if digest.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise ModelDownloadError(
            f"{dest.name}: SHA-256 mismatch (file corrupted or manifest outdated). Try again later."
        )
    part.replace(dest)


def ensure_model(
    model_id: str,
    manifest_url: str,
    data_dir: Path,
    platform: str = "windows",
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    try:
        manifest = _fetch_manifest(manifest_url)
    except ModelDownloadError:
        local = _newest_complete(Path(data_dir) / "models" / model_id)
        if local is not None:  # offline: use what is already on disk
            return local
        raise
    entry = next(
        (m for m in manifest.get("models", []) if m["id"] == model_id and m["platform"] == platform), None
    )
    if entry is None:
        raise ModelNotFound(f"Model '{model_id}' for {platform} is not in the manifest at {manifest_url}.")
    model_dir = Path(data_dir) / "models" / model_id / entry["version"]
    missing = [
        f for f in entry["files"]
        if not (model_dir / f["path"]).is_file() or (model_dir / f["path"]).stat().st_size != f["size"]
    ]
    total = sum(f["size"] for f in missing)
    done = 0

    def on_bytes(n: int) -> None:
        nonlocal done
        done += n
        if progress is not None:
            progress(done, total)

    for f in missing:
        _download(f["url"], model_dir / f["path"], f["sha256"], on_bytes)
    (model_dir / COMPLETE).write_text(entry["version"], encoding="utf-8")
    return model_dir


def _newest_complete(model_root: Path) -> Path | None:
    done = [d for d in model_root.glob("*") if (d / COMPLETE).is_file()] if model_root.is_dir() else []
    return max(done, key=lambda d: (d / COMPLETE).stat().st_mtime) if done else None
