"""Build manifest.json for exported models and stage them for upload.

Usage:
  python -m models.manifest --base-url https://huggingface.co/<owner>/<repo>/resolve/main --version 1 \\
      --stage models/out/hf
Collects every models/out/*-ct2 and *-onnx export (with screentrans_model.json), copies them to
<stage>/<id>/<format>/<version>/... and writes <stage>/manifest.json.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Callable

OUT = Path(__file__).parent / "out"
META_FILE = "screentrans_model.json"
PLATFORM = {"ct2": "windows", "onnx": "android"}
LICENSES = {"opus-mt-en-vi": "apache-2.0", "vinai-en2vi": "agpl-3.0"}  # from the HF model cards


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


AssetUrl = Callable[[str, str, str, str], str]  # (id, format, version, relative path) -> url


def github_asset_name(model_id: str, fmt: str, rel: str) -> str:
    """Release assets are flat: encode the folder layout in the file name."""
    return f"{model_id}__{fmt}__{rel.replace('/', '__')}"


def github_asset_url(repo: str) -> AssetUrl:
    def url(model_id: str, fmt: str, version: str, rel: str) -> str:
        return (f"https://github.com/{repo}/releases/download/models-v{version}/"
                f"{github_asset_name(model_id, fmt, rel)}")
    return url


def build_manifest(export_dirs: list[Path], base_url: str, version: str, licenses: dict[str, str],
                   asset_url: AssetUrl | None = None) -> dict:
    if asset_url is None:
        def asset_url(model_id: str, fmt: str, ver: str, rel: str) -> str:
            return f"{base_url.rstrip('/')}/{model_id}/{fmt}/{ver}/{rel}"
    models = []
    for d in export_dirs:
        meta = json.loads((d / META_FILE).read_text(encoding="utf-8"))
        files = []
        for p in sorted(x for x in d.rglob("*") if x.is_file()):
            rel = p.relative_to(d).as_posix()
            files.append({"path": rel, "url": asset_url(meta["id"], meta["format"], version, rel),
                          "sha256": _sha256(p), "size": p.stat().st_size})
        models.append({
            "id": meta["id"], "platform": PLATFORM[meta["format"]], "format": meta["format"],
            "version": version, "license": licenses[meta["id"]], "files": files,
        })
    return {"version": 1, "models": models}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="")
    ap.add_argument("--github-release", metavar="OWNER/REPO",
                    help="flat asset names for a GitHub release models-v<version> instead of folders")
    ap.add_argument("--version", required=True)
    ap.add_argument("--stage", type=Path, required=True)
    args = ap.parse_args()
    exports = sorted(d for d in OUT.iterdir() if d.is_dir() and (d / META_FILE).is_file())
    asset_url = github_asset_url(args.github_release) if args.github_release else None
    manifest = build_manifest(exports, args.base_url, args.version, LICENSES, asset_url=asset_url)
    args.stage.mkdir(parents=True, exist_ok=True)
    for d, m in zip(exports, manifest["models"]):
        if args.github_release:
            for f in m["files"]:
                shutil.copy2(d / f["path"], args.stage / github_asset_name(m["id"], m["format"], f["path"]))
        else:
            shutil.copytree(d, args.stage / m["id"] / m["format"] / args.version, dirs_exist_ok=True)
    (args.stage / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"Staged {len(manifest['models'])} models in {args.stage}")


if __name__ == "__main__":
    main()
