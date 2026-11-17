import functools
import hashlib
import http.server
import json
import threading

import pytest

from app.models import ModelDownloadError, ensure_model
from app.translate.base import ModelNotFound


class _CountingHandler(http.server.SimpleHTTPRequestHandler):
    requests: list[str] = []

    def do_GET(self):
        type(self).requests.append(self.path)
        super().do_GET()

    def log_message(self, *args):
        pass


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    _CountingHandler.requests = []
    handler = functools.partial(_CountingHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _publish(root, base, files: dict[str, bytes], sha_override: dict[str, str] | None = None):
    entries = []
    for path, content in files.items():
        dest = root / "m" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        sha = (sha_override or {}).get(path) or hashlib.sha256(content).hexdigest()
        entries.append({"path": path, "url": f"{base}/m/{path}", "sha256": sha, "size": len(content)})
    manifest = {"version": 1, "models": [{
        "id": "tiny", "platform": "windows", "format": "ct2", "version": "1", "license": "apache-2.0", "files": entries}]}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return f"{base}/manifest.json"


FILES = {"model.bin": b"weights" * 100, "sub/vocab.json": b'{"a": 1}'}


def test_downloads_all_files(server, tmp_path):
    root, base = server
    url = _publish(root, base, FILES)
    model_dir = ensure_model("tiny", url, tmp_path / "data")
    assert model_dir == tmp_path / "data" / "models" / "tiny" / "1"
    assert (model_dir / "model.bin").read_bytes() == FILES["model.bin"]
    assert (model_dir / "sub" / "vocab.json").read_bytes() == FILES["sub/vocab.json"]


def test_second_call_does_not_download_again(server, tmp_path):
    root, base = server
    url = _publish(root, base, FILES)
    ensure_model("tiny", url, tmp_path / "data")
    _CountingHandler.requests = []
    ensure_model("tiny", url, tmp_path / "data")
    assert _CountingHandler.requests == ["/manifest.json"]


def test_sha_mismatch_leaves_no_file(server, tmp_path):
    root, base = server
    url = _publish(root, base, FILES, sha_override={"model.bin": "0" * 64})
    with pytest.raises(ModelDownloadError, match="model.bin"):
        ensure_model("tiny", url, tmp_path / "data")
    leftovers = [p.name for p in (tmp_path / "data").rglob("*") if p.is_file()]
    assert not any(n == "model.bin" or n.endswith(".part") for n in leftovers)


def test_unknown_model_id(server, tmp_path):
    root, base = server
    url = _publish(root, base, FILES)
    with pytest.raises(ModelNotFound):
        ensure_model("nope", url, tmp_path / "data")


def test_network_error_mentions_model_dir(tmp_path):
    with pytest.raises(ModelDownloadError, match="--model-dir"):
        ensure_model("tiny", "http://127.0.0.1:1/manifest.json", tmp_path / "data")


def test_progress_callback(server, tmp_path):
    root, base = server
    url = _publish(root, base, FILES)
    seen = []
    ensure_model("tiny", url, tmp_path / "data", progress=lambda done, total: seen.append((done, total)))
    total = sum(len(v) for v in FILES.values())
    assert seen and seen[-1] == (total, total)


class _TruncatingHandler(_CountingHandler):
    def do_GET(self):
        type(self).requests.append(self.path)
        if self.path.endswith("model.bin"):
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            self.wfile.write(b"x" * 10)
            self.wfile.flush()
            self.close_connection = True
            return
        http.server.SimpleHTTPRequestHandler.do_GET(self)


def test_connection_dropped_mid_file(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    handler = functools.partial(_TruncatingHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = _publish(root, f"http://127.0.0.1:{httpd.server_address[1]}", FILES)
        with pytest.raises(ModelDownloadError, match="model.bin"):
            ensure_model("tiny", url, tmp_path / "data")
        assert not [p for p in (tmp_path / "data").rglob("*.part")]
    finally:
        httpd.shutdown()


def test_offline_uses_previously_downloaded_model(server, tmp_path):
    root, base = server
    first = ensure_model("tiny", _publish(root, base, FILES), tmp_path / "data")
    assert ensure_model("tiny", "http://127.0.0.1:1/manifest.json", tmp_path / "data") == first


def test_offline_ignores_incomplete_download(tmp_path):
    partial = tmp_path / "data" / "models" / "tiny" / "1"
    partial.mkdir(parents=True)
    (partial / "model.bin").write_bytes(b"half")
    with pytest.raises(ModelDownloadError):
        ensure_model("tiny", "http://127.0.0.1:1/manifest.json", tmp_path / "data")
