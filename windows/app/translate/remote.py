"""Remote LLM clients (Phase 5): Gemini / OpenAI / Kaggle over stdlib HTTP, Claude through the official SDK.

Every client turns (system, user) into the model's reply text; errors become RemoteError with a kind and a
message that never contains the key or the request.
"""
import http.client
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Literal, Protocol

from app.translate.llm_prompt import REPLY_SCHEMA

Kind = Literal["auth", "quota", "timeout", "network", "server", "bad_reply"]
NAMES = {"gemini": "Gemini", "openai": "OpenAI", "claude": "Claude", "kaggle": "Kaggle"}
DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "openai": "gpt-5-mini", "claude": "claude-opus-5-5", "kaggle": "server"}
MAX_TOKENS = 4096


class RemoteError(Exception):
    def __init__(self, kind: Kind, provider: str, detail: str = ""):
        self.kind = kind
        super().__init__(f"{provider}: {kind}" + (f" ({detail})" if detail else ""))


class Client(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, timeout_s: float) -> str: ...


def _kind_for_status(status: int) -> Kind:
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "quota"
    if status == 408:
        return "timeout"
    return "server"


class _HttpClient:
    name = ""

    def __init__(self, key: str, model: str, opener: Callable | None):
        self.key, self.model = key, model
        self._open = opener or urllib.request.urlopen

    def _post(self, url: str, headers: dict, body: dict, timeout_s: float) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            raw = self._open(req, timeout=timeout_s).read()
        except urllib.error.HTTPError as e:
            kind = _kind_for_status(e.code)
            if kind == "server":
                try:
                    body = e.read()
                except Exception:
                    body = b""
                kind = self._auth_hint(e.code, body or b"") or kind
            raise RemoteError(kind, self.name, f"HTTP {e.code}") from None
        except (ValueError, UnicodeError):  # the key cannot go in a header: a broken key (message would show it)
            raise RemoteError("auth", self.name) from None
        except http.client.HTTPException:  # truncated / garbled response (flaky tunnel)
            raise RemoteError("network", self.name) from None
        except (socket.timeout, TimeoutError):
            raise RemoteError("timeout", self.name) from None
        except urllib.error.URLError as e:
            kind: Kind = "timeout" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "network"
            raise RemoteError(kind, self.name) from None
        except OSError:
            raise RemoteError("network", self.name) from None
        try:
            return json.loads(raw)
        except ValueError:
            raise RemoteError("bad_reply", self.name) from None

    def _auth_hint(self, status: int, body: bytes) -> Kind | None:
        """Providers that report a wrong key with another status (the body is never shown)."""
        return None

    def _pick(self, data, *path) -> str:
        try:
            for p in path:
                data = data[p]
        except (KeyError, IndexError, TypeError):
            raise RemoteError("bad_reply", self.name) from None
        if not isinstance(data, str):
            raise RemoteError("bad_reply", self.name)
        return data


class GeminiClient(_HttpClient):
    name = "Gemini"

    def _auth_hint(self, status: int, body: bytes) -> Kind | None:
        return "auth" if status == 400 and (b"API_KEY_INVALID" in body or b"API key not valid" in body) else None

    def complete(self, system: str, user: str, timeout_s: float) -> str:
        data = self._post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": self.key},
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"responseMimeType": "application/json",
                                  "thinkingConfig": {"thinkingBudget": 0}}},  # translation: no reasoning, fast
            timeout_s)
        return self._pick(data, "candidates", 0, "content", "parts", 0, "text")


class OpenAiClient(_HttpClient):
    name = "OpenAI"

    def complete(self, system: str, user: str, timeout_s: float) -> str:
        data = self._post(
            "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {self.key}"},
            {"model": self.model, "response_format": {"type": "json_object"}, "reasoning_effort": "minimal",
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout_s)
        return self._pick(data, "choices", 0, "message", "content")


class KaggleClient(_HttpClient):
    """Our own server (training/kaggle_serve.ipynb): it receives the built prompt and answers
    {"translations": [...]}; the reply is handed back as JSON text so parsing stays shared."""
    name = "Kaggle"

    def __init__(self, key: str, model: str, url: str, opener: Callable | None):
        super().__init__(key, model, opener)
        self.url = url.rstrip("/")

    def complete(self, system: str, user: str, timeout_s: float) -> str:
        if not self.url:
            raise RemoteError("network", self.name, "chưa có URL server")
        data = self._post(f"{self.url}/translate", {"Authorization": f"Bearer {self.key}"},
                          {"system": system, "prompt": user, "source_lang": "en"}, timeout_s)
        if not isinstance(data, dict) or not isinstance(data.get("translations"), list):
            raise RemoteError("bad_reply", self.name)
        return json.dumps({"translations": data["translations"]}, ensure_ascii=False)


class ClaudeClient:
    name = "Claude"

    def __init__(self, key: str, model: str, http_client=None):
        import anthropic

        self.model = model
        self._anthropic = anthropic
        kwargs = {"http_client": http_client} if http_client is not None else {}
        self._client = anthropic.Anthropic(api_key=key, max_retries=0, **kwargs)  # our own fallback handles failures

    def complete(self, system: str, user: str, timeout_s: float) -> str:
        a = self._anthropic
        try:
            msg = self._client.beta.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                timeout=timeout_s)
        except (a.AuthenticationError, a.PermissionDeniedError):
            raise RemoteError("auth", self.name) from None
        except a.RateLimitError:
            raise RemoteError("quota", self.name) from None
        except a.APITimeoutError:
            raise RemoteError("timeout", self.name) from None
        except a.APIConnectionError:
            raise RemoteError("network", self.name) from None
        except a.APIStatusError as e:
            raise RemoteError(_kind_for_status(e.status_code), self.name, f"HTTP {e.status_code}") from None
        if msg.stop_reason in ("refusal", "max_tokens"):
            raise RemoteError("bad_reply", self.name, msg.stop_reason)
        text = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise RemoteError("bad_reply", self.name)
        return text


def make_client(engine: str, key: str, model: str = "", url: str = "", opener: Callable | None = None,
                http_client=None) -> Client:
    # a pasted key often carries spaces, a newline or zero-width characters; keys never contain them
    key = "".join(ch for ch in (key or "") if not ch.isspace() and ch not in "​‌‍⁠﻿")
    model = (model or "").strip() or DEFAULT_MODELS.get(engine, "")
    if engine == "gemini":
        return GeminiClient(key, model, opener)
    if engine == "openai":
        return OpenAiClient(key, model, opener)
    if engine == "kaggle":  # the server's host names it: each server gets its own cache namespace
        url = url.strip()
        host = urllib.parse.urlparse(url).netloc or "server"
        return KaggleClient(key, host, url, opener)
    if engine == "claude":
        return ClaudeClient(key, model, http_client)
    raise ValueError(f"not a remote engine: {engine}")
