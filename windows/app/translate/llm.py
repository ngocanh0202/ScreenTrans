"""Translate with a remote LLM (Phase 5): context of the previous lines, the speaker, the game's glossary.

`translate_ctx` returns None whenever the remote engine cannot be used (failure, back-off, wrong key, daily
limit, unusable reply): the Pipeline then translates those sentences with the local model as usual (with
glossary placeholders) and does not cache them under the remote engine's name.
"""
import time
from typing import Callable

from app.translate.base import Translator
from app.translate.llm_prompt import CONTEXT_MAX, build_messages, parse_reply
from app.translate.remote import Client, RemoteError
from app.usage import Usage

RETRY_AFTER_S = 30.0
REASONS = {"timeout": "quá thời gian", "network": "không kết nối được", "server": "server lỗi",
           "quota": "hết hạn mức / quá nhiều yêu cầu", "bad_reply": "trả lời không hợp lệ"}


class LlmTranslator:
    prefers_batch = True  # Live: all sentences of one OCR in one call

    def __init__(self, engine: str, client: Client, local: Translator, usage: Usage, daily_limit: int,
                 notify: Callable[[str], None], clock: Callable[[], float] = time.monotonic):
        self.engine, self.client, self.local = engine, client, local
        self.model_id = f"{engine}:{client.model}"
        self.usage, self.daily_limit = usage, daily_limit
        self._notify, self._clock = notify, clock
        self.timeout_s = 6.0
        self._context: list[str] = []
        self._speaker: str | None = None
        self._blocked = False          # wrong key: never call again (a new translator is made when it changes)
        self._retry_at = 0.0           # after a failure: local until then
        self._failing = False          # one notice per failure spell
        self._limit_day = ""           # one limit notice per day

    def set_speaker(self, name: str | None) -> None:
        self._speaker = name

    def translate(self, texts: list[str]) -> list[str]:
        out = self.translate_ctx(texts, {})
        return out if out is not None else self.local.translate(texts)

    def translate_ctx(self, texts: list[str], glossary: dict[str, str | None]) -> list[str] | None:
        if not texts:
            return []
        if self._blocked or self._clock() < self._retry_at:
            return None
        chars = sum(len(t) for t in texts)
        if not self.usage.allows(chars, self.daily_limit):
            today = time.strftime("%Y-%m-%d")
            if self._limit_day != today:
                self._limit_day = today
                self._notify(f"{self.client.name}: đã tới giới hạn {self.daily_limit} ký tự hôm nay — "
                             f"dùng model trên máy.")
            return None
        system, user = build_messages(texts, self._context, self._speaker, glossary)
        try:
            reply = self.client.complete(system, user, self.timeout_s)
        except RemoteError as e:
            self._fail(e)
            return None
        self.usage.add(chars)
        out = parse_reply(reply, len(texts))
        if out is None:
            return None  # this batch only: the next one tries the server again
        self._failing = False
        self._context = (self._context + texts)[-CONTEXT_MAX:]
        return out

    def _fail(self, e: RemoteError) -> None:
        name = self.client.name
        if e.kind == "auth":
            self._blocked = True
            self._notify(f"{name}: sai key hoặc hết quyền — mở Cài đặt để sửa. Đang dùng model trên máy.")
            return
        self._retry_at = self._clock() + RETRY_AFTER_S
        if not self._failing:
            self._failing = True
            self._notify(f"{name}: {REASONS.get(e.kind, e.kind)} — dùng model trên máy.")
