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
