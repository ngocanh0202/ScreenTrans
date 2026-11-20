"""Build manifest.json for exported models and stage them for upload.

Usage (the app reads https://huggingface.co/anhbui02/screentrans-models/resolve/main/manifest.json):
  python -m models.manifest --version 2026-11-25 --stage models/out/hf --only screentrans-en-vi \\
      --merge-from https://huggingface.co/anhbui02/screentrans-models/resolve/main/manifest.json \\
      --upload anhbui02/screentrans-models            # prints what it would upload
  ... --upload anhbui02/screentrans-models --yes      # uploads (write token in HF_TOKEN)
Collects the models/out/*-ct2 and *-onnx exports (with screentrans_model.json), copies them to
<stage>/<id>/<format>/<version>/... and writes <stage>/manifest.json; --merge-from keeps the other models already
published (a new model or version replaces only its own entry).
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
LICENSES = {"opus-mt-en-vi": "apache-2.0", "vinai-en2vi": "agpl-3.0",  # from the HF model cards
            "screentrans-en-vi": "apache-2.0"}  # Phase 6: opus-mt fine-tuned on open data (CC BY data, credited)
LABELS = {"opus-mt-en-vi": "opus-mt (nhanh)", "vinai-en2vi": "vinai (chất lượng hơn, chậm hơn)",
          "screentrans-en-vi": "ScreenTrans (opus-mt tinh chỉnh cho thoại game)"}
DEFAULT_REPO = "anhbui02/screentrans-models"


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
        entry = {
            "id": meta["id"], "platform": PLATFORM[meta["format"]], "format": meta["format"],
            "version": version, "license": licenses[meta["id"]], "files": files,
        }
        if meta["id"] in LABELS:
            entry["label"] = LABELS[meta["id"]]
        models.append(entry)
    return {"version": 1, "models": models}


def merge_manifest(old: dict | None, new: dict) -> dict:
    """The published manifest with the new entries: an entry replaces the one with its id and platform."""
    fresh = {(m["id"], m["platform"]) for m in new["models"]}
    kept = [m for m in (old or {}).get("models", []) if (m.get("id"), m.get("platform")) not in fresh]
    return {"version": 1, "models": kept + new["models"]}


def upload(stage: Path, repo: str, api) -> None:
    """The staged folders and manifest.json to a Hugging Face model repo (created when missing)."""
    api.create_repo(repo, repo_type="model", exist_ok=True)
    api.upload_folder(folder_path=str(stage), repo_id=repo, repo_type="model", commit_message="ScreenTrans models")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="")
    ap.add_argument("--github-release", metavar="OWNER/REPO",
                    help="flat asset names for a GitHub release models-v<version> instead of folders")
    ap.add_argument("--version", required=True)
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--only", default="", help="comma-separated model ids (default: every export)")
    ap.add_argument("--merge-from", default="", help="the published manifest.json (URL or file): keep its other models")
    ap.add_argument("--upload", metavar="OWNER/REPO", default="", help=f"Hugging Face repo (e.g. {DEFAULT_REPO})")
    ap.add_argument("--yes", action="store_true", help="really upload (write token in HF_TOKEN)")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    exports = sorted(d for d in OUT.iterdir() if d.is_dir() and (d / META_FILE).is_file()
                     and (not only or json.loads((d / META_FILE).read_text(encoding="utf-8"))["id"] in only))
    asset_url = github_asset_url(args.github_release) if args.github_release else None
    base_url = args.base_url or (f"https://huggingface.co/{args.upload}/resolve/main" if args.upload else "")
    manifest = build_manifest(exports, base_url, args.version, LICENSES, asset_url=asset_url)
    new_entries = manifest
    if args.merge_from:
        manifest = merge_manifest(_read_json(args.merge_from), manifest)
    args.stage.mkdir(parents=True, exist_ok=True)
    for d, m in zip(exports, manifest["models"]):
        if args.github_release:
            for f in m["files"]:
                shutil.copy2(d / f["path"], args.stage / github_asset_name(m["id"], m["format"], f["path"]))
        else:
            shutil.copytree(d, args.stage / m["id"] / m["format"] / args.version, dirs_exist_ok=True)
    (args.stage / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                                              encoding="utf-8")
    print(f"Staged {len(new_entries['models'])} model(s) in {args.stage}; the manifest lists {len(manifest['models'])}")
    if args.upload:
        size = sum(f["size"] for m in new_entries["models"] for f in m["files"])
        print(f"Upload to https://huggingface.co/{args.upload}: {size / 1e6:.0f} MB")
        if not args.yes:
            print("Nothing uploaded. Add --yes to upload (write token in the HF_TOKEN environment variable).")
            return
        import os

        from huggingface_hub import HfApi

        upload(args.stage, args.upload, HfApi(token=os.environ.get("HF_TOKEN") or None))
        print("uploaded")


def _read_json(src: str) -> dict | None:
    """A published manifest; missing (the first upload) -> None."""
    import urllib.error
    import urllib.request

    try:
        if src.startswith("http"):
            with urllib.request.urlopen(src, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        return json.loads(Path(src).read_text(encoding="utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


if __name__ == "__main__":
    main()
