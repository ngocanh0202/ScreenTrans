"""Remote LLM clients: request shape and error mapping, with fake transports (no network)."""
import io
import json
import socket
import urllib.error

import httpx2
import pytest

from app.translate.remote import DEFAULT_MODELS, RemoteError, make_client

KEY = "sk-SECRET-123"


class Opener:
    """urllib stand-in: records the request, answers with (status, body) or raises."""

    def __init__(self, status=200, body=b"", exc=None):
        self.status, self.body, self.exc = status, body, exc
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append((req, timeout))
        if self.exc is not None:
            raise self.exc
        if self.status >= 400:
            raise urllib.error.HTTPError(req.full_url, self.status, "err", {}, io.BytesIO(self.body))
        return io.BytesIO(self.body)


def gemini_ok(text):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()


def openai_ok(text):
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode()


REPLY = '{"translations": ["Chào."]}'
OK = {"gemini": gemini_ok(REPLY), "openai": openai_ok(REPLY),
      "kaggle": json.dumps({"translations": ["Chào."]}).encode()}


def client(engine, opener, key=KEY):
    return make_client(engine, key, url="https://abc.ngrok.app", opener=opener)


@pytest.mark.parametrize("engine", ["gemini", "openai", "kaggle"])
def test_http_clients_return_the_reply_text(engine):
    op = Opener(body=OK[engine])
    out = client(engine, op).complete("SYS", 'Dịch các câu sau:\n["Hi."]', 6.0)
    assert json.loads(out)["translations"] == ["Chào."]
    req, timeout = op.requests[0]
    assert timeout == 6.0 and req.get_method() == "POST"


def test_gemini_request_shape():
    op = Opener(body=OK["gemini"])
    make_client("gemini", KEY, opener=op).complete("SYS", "USER", 2.5)
    req = op.requests[0][0]
    assert req.full_url == f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODELS['gemini']}:generateContent"
    assert req.get_header("X-goog-api-key") == KEY
    body = json.loads(req.data)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["contents"][0]["parts"][0]["text"] == "USER"
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_openai_request_shape_and_stripped_key():  # RF2
    op = Opener(body=OK["openai"])
    make_client("openai", "  sk-x\n", model="my-model", opener=op).complete("SYS", "USER", 2.5)
    req = op.requests[0][0]
    assert req.full_url == "https://api.openai.com/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sk-x"
    body = json.loads(req.data)
    assert body["model"] == "my-model" and body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]


def test_kaggle_request_carries_the_sentences_and_token():
    op = Opener(body=OK["kaggle"])
    make_client("kaggle", "tok", url="https://abc.ngrok.app/", opener=op).complete("SYS", 'Dịch các câu sau:\n["Hi."]', 6)
    req = op.requests[0][0]
    assert req.full_url == "https://abc.ngrok.app/translate"
    assert req.get_header("Authorization") == "Bearer tok"
    body = json.loads(req.data)
    assert body["system"] == "SYS" and body["prompt"] == 'Dịch các câu sau:\n["Hi."]' and body["source_lang"] == "en"


@pytest.mark.parametrize("engine", ["gemini", "openai", "kaggle"])
@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (429, "quota"), (500, "server"), (503, "server")])
def test_http_errors_map_to_kinds(engine, status, kind):
    with pytest.raises(RemoteError) as e:
        client(engine, Opener(status=status, body=f'{{"error": "bad key {KEY}"}}'.encode())).complete("S", "U", 1)
    assert e.value.kind == kind
    assert KEY not in str(e.value)  # RF5


@pytest.mark.parametrize("exc,kind", [(socket.timeout("timed out"), "timeout"), (TimeoutError(), "timeout"),
                                      (urllib.error.URLError(socket.timeout()), "timeout"),
                                      (urllib.error.URLError(f"no route {KEY}"), "network")])
def test_transport_errors_map_to_kinds(exc, kind):
    with pytest.raises(RemoteError) as e:
        client("openai", Opener(exc=exc)).complete("S", "U", 1)
    assert e.value.kind == kind and KEY not in str(e.value)


@pytest.mark.parametrize("engine", ["gemini", "openai"])
def test_garbage_body_is_a_bad_reply(engine):
    with pytest.raises(RemoteError) as e:
        client(engine, Opener(body=b"<html>oops</html>")).complete("S", "U", 1)
    assert e.value.kind == "bad_reply"


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError):
        make_client("local", KEY)


# ---- Claude (official SDK, fake transport) ----------------------------------------------------------------
def claude(handler, model=""):
    return make_client("claude", KEY, model=model, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def message(text, stop="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_claude_request_and_reply():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx2.Response(200, json=message(REPLY))

    assert claude(handler).complete("SYS", "USER", 6.0) == REPLY
    req = seen[0]
    body = json.loads(req.content)
    assert req.url.path == "/v1/messages"
    assert KEY in (req.headers.get("x-api-key", ""), req.headers.get("authorization", "").removeprefix("Bearer "))
    assert body["model"] == "claude-opus-5-5" == DEFAULT_MODELS["claude"]
    assert body["system"] == "SYS" and body["messages"] == [{"role": "user", "content": "USER"}]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (429, "quota"), (500, "server"), (529, "server")])
def test_claude_errors_map_to_kinds(status, kind):
    def handler(request):
        return httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": f"bad {KEY}"}})

    with pytest.raises(RemoteError) as e:
        claude(handler).complete("S", "U", 1)
    assert e.value.kind == kind and KEY not in str(e.value)


def test_claude_timeout_and_refusal():
    def slow(request):
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(RemoteError) as e:
        claude(slow).complete("S", "U", 1)
    assert e.value.kind == "timeout"

    def refuse(request):
        return httpx2.Response(200, json=message("", stop="refusal"))

    with pytest.raises(RemoteError) as e:
        claude(refuse).complete("S", "U", 1)
    assert e.value.kind == "bad_reply"
