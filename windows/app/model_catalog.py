"""What Settings → Model shows for each model (rules: shared/fixtures/model_catalog; Kotlin ModelCatalog.kt passes
the same files): the manifest's models for this platform, the ones on disk, the bundled one (Android)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRow:
    id: str
    label: str
    status: str          # "bundled" | "update" | "installed" | "missing"
    version: str | None  # the version used on this device (None: not on it)
    latest: str | None   # the manifest's version (None: not in the manifest)
    download: int        # bytes to download (0 when nothing to download)
    deletable: bool      # a downloaded copy exists (a bundled model is never deleted)
    active: bool


def catalog(manifest: list[dict], installed: dict[str, list[str]], bundled: dict[str, str], active: str) -> list[ModelRow]:
    rows = []
    ids = [m["id"] for m in manifest] + sorted((set(installed) | set(bundled)) - {m["id"] for m in manifest})
    by_id = {m["id"]: m for m in manifest}
    for mid in ids:
        m = by_id.get(mid)
        versions = list(installed.get(mid, []))
        have = set(versions) | ({bundled[mid]} if mid in bundled else set())
        latest = m["version"] if m else None
        if have and latest is not None and latest not in have:
            status = "update"
        elif have:
            status = "installed" if versions and (latest is None or latest in versions) else "bundled"
        else:
            status = "missing"
        version = max(versions) if versions else bundled.get(mid)
        size = sum(int(f.get("size", 0)) for f in m["files"]) if m and status in ("missing", "update") else 0
        rows.append(ModelRow(mid, (m or {}).get("label") or mid, status, version, latest, size, bool(versions),
                             mid == active))
    return rows
