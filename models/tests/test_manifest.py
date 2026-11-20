import hashlib
import json
from pathlib import Path

import jsonschema

from models.manifest import build_manifest

SCHEMA = Path(__file__).parents[2] / "shared" / "schemas" / "model-manifest.schema.json"


def _export(tmp_path, name, meta, files):
    d = tmp_path / name
    for path, content in files.items():
        (d / path).parent.mkdir(parents=True, exist_ok=True)
        (d / path).write_bytes(content)
    (d / "screentrans_model.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


def test_build_manifest(tmp_path):
    ct2 = _export(tmp_path, "vinai-ct2", {"id": "vinai-en2vi", "format": "ct2"}, {"model.bin": b"abc"})
    onnx = _export(tmp_path, "opus-onnx", {"id": "opus-mt-en-vi", "format": "onnx"}, {"x/enc.onnx": b"zz"})
    m = build_manifest([ct2, onnx], "https://hf.example/r/resolve/main", "3",
                       {"vinai-en2vi": "agpl-3.0", "opus-mt-en-vi": "apache-2.0"})
    jsonschema.validate(m, json.loads(SCHEMA.read_text(encoding="utf-8")))
    vinai = next(x for x in m["models"] if x["id"] == "vinai-en2vi")
    assert (vinai["platform"], vinai["format"], vinai["version"], vinai["license"]) == ("windows", "ct2", "3", "agpl-3.0")
    f = next(x for x in vinai["files"] if x["path"] == "model.bin")
    assert f == {"path": "model.bin", "url": "https://hf.example/r/resolve/main/vinai-en2vi/ct2/3/model.bin",
                 "sha256": hashlib.sha256(b"abc").hexdigest(), "size": 3}
    opus = next(x for x in m["models"] if x["id"] == "opus-mt-en-vi")
    assert opus["platform"] == "android"
    assert any(x["path"] == "x/enc.onnx" for x in opus["files"])


def test_github_release_asset_urls(tmp_path):
    from models.manifest import github_asset_name, github_asset_url

    ct2 = _export(tmp_path, "vinai-ct2", {"id": "vinai-en2vi", "format": "ct2"},
                  {"model.bin": b"abc", "sub/vocab.json": b"{}"})
    onnx = _export(tmp_path, "opus-onnx", {"id": "opus-mt-en-vi", "format": "onnx"}, {"sub/vocab.json": b"{}"})
    m = build_manifest([ct2, onnx], "", "3", {"vinai-en2vi": "agpl-3.0", "opus-mt-en-vi": "apache-2.0"},
                       asset_url=github_asset_url("ngocanh0202/ScreenTrans"))
    jsonschema.validate(m, json.loads(SCHEMA.read_text(encoding="utf-8")))
    vinai = next(x for x in m["models"] if x["id"] == "vinai-en2vi")
    vocab = next(f for f in vinai["files"] if f["path"] == "sub/vocab.json")
    assert vocab["url"] == ("https://github.com/ngocanh0202/ScreenTrans/releases/download/models-v3/"
                            "vinai-en2vi__ct2__sub__vocab.json")
    urls = [f["url"] for x in m["models"] for f in x["files"]]
    assert len(urls) == len(set(urls))
    assert github_asset_name("opus-mt-en-vi", "onnx", "sub/vocab.json") == "opus-mt-en-vi__onnx__sub__vocab.json"


def test_default_manifest_url_points_to_hugging_face():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parents[2] / "windows"))
    from app.config import load_config

    url = load_config(None).models.manifest_url
    assert url == "https://huggingface.co/anhbui02/screentrans-models/resolve/main/manifest.json"
    assert load_config(Path(__file__).parents[2] / "windows" / "config.yaml").models.manifest_url == url


def test_an_old_config_with_the_github_url_moves_to_hugging_face(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).parents[2] / "windows"))
    from app.config import OLD_MANIFEST_URL, load_config

    cfg = tmp_path / "config.yaml"
    cfg.write_text(f'models:\n  manifest_url: "{OLD_MANIFEST_URL}"\n', encoding="utf-8")
    assert "huggingface.co/anhbui02/screentrans-models" in load_config(cfg).models.manifest_url


def test_merge_keeps_other_models_and_replaces_the_same_id_and_platform():
    from models.manifest import merge_manifest

    old = {"version": 1, "models": [{"id": "opus-mt-en-vi", "platform": "windows", "version": "1"},
                                    {"id": "opus-mt-en-vi", "platform": "android", "version": "1"},
                                    {"id": "screentrans-en-vi", "platform": "windows", "version": "a"}]}
    new = {"version": 1, "models": [{"id": "screentrans-en-vi", "platform": "windows", "version": "b"}]}
    got = merge_manifest(old, new)
    assert [(m["id"], m["platform"], m["version"]) for m in got["models"]] == [
        ("opus-mt-en-vi", "windows", "1"), ("opus-mt-en-vi", "android", "1"), ("screentrans-en-vi", "windows", "b")]
    assert merge_manifest(None, new) == new


def test_labels_and_upload(tmp_path):
    from models.manifest import build_manifest, upload

    d = _export(tmp_path, "st-ct2", {"id": "screentrans-en-vi", "format": "ct2"}, {"model.bin": b"x"})
    m = build_manifest([d], "https://huggingface.co/anhbui02/screentrans-models/resolve/main", "2026-11-25",
                       {"screentrans-en-vi": "apache-2.0"})
    jsonschema.validate(m, json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert m["models"][0]["label"].startswith("ScreenTrans")
    calls = []

    class Api:
        def create_repo(self, repo, **kw):
            calls.append(("create", repo, kw.get("exist_ok")))

        def upload_folder(self, **kw):
            calls.append(("upload", kw["repo_id"], kw["folder_path"]))

    upload(tmp_path, "anhbui02/screentrans-models", Api())
    assert calls == [("create", "anhbui02/screentrans-models", True),
                     ("upload", "anhbui02/screentrans-models", str(tmp_path))]
