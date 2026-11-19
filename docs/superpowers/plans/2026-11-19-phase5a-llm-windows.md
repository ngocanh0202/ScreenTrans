# Phase 5a — Dịch bằng mô hình ngôn ngữ lớn từ xa (Windows) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per game, translate with Gemini / OpenAI / Claude / a Kaggle server instead of the local model, with context, glossary, fallback to the local model, encrypted keys and a daily character limit — Windows first; prompt and reply rules in shared fixtures so Android (5b) ports them.

**Architecture:** `LlmTranslator` wraps a provider client and the local `Ct2Translator`; it implements the existing `Translator` protocol plus an optional `translate_ctx(texts, glossary)` that the Pipeline calls when present (glossary as a term list in the prompt instead of placeholders). Prompt building and reply parsing are pure functions specified by `shared/fixtures/llm/`. The worker swaps the pipeline's translator per game (`set_game` payload `engine`) like it already swaps the OCR engine, and sets the timeout per job kind.

**Tech Stack:** Python 3.11, PySide6, stdlib `urllib` (Gemini / OpenAI / Kaggle), official `anthropic` SDK (Claude), `ctypes` DPAPI.

**Spec:** `AGENT.md` §7 "Engine từ xa tùy chọn" and §15 Phase 5 (first bullet).

## Global Constraints

- `translator.engine` per game: `local` (default) | `gemini` | `openai` | `claude` | `kaggle`; unknown → `local`.
- Order stays `overrides` → cache → engine; the cache namespace includes engine + model (`model_id` = `"<engine>:<model>"`).
- Prompt carries: the 2–3 previous dialogue sentences, the speaker name when known, the game glossary (keep / map), "dịch tự nhiên, đúng giọng nhân vật, giữ nguyên tên riêng"; reply = JSON, one translation per sentence; all sentences of one OCR in one call.
- Timeouts: 2.5 s for Live jobs, 6 s for one-shot jobs. Error / quota / timeout → translate locally at once, notify once; retry the server after 30 s. Wrong key (401/403) → clear message, no retry until the key changes.
- Keys: entered in settings, stored with DPAPI in `data_dir`; never in logs, notices, `translations.jsonl` or exception text shown to the user.
- Privacy & cost: warn that game text is sent to the provider; daily character limit (default 50 000, configurable); show characters used today.
- Text only leaves the machine when the game's engine is not `local`.
- Claude: official `anthropic` SDK, default model `claude-opus-5-5`, `output_config.effort: "low"`, `output_config.format` JSON schema, server-side fallbacks (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`), `max_retries=0` (our own fallback handles failures). Model name editable (e.g. `claude-haiku-5-5` is ~40× cheaper — the user's choice).
- Gemini / OpenAI / Kaggle: raw HTTP with `urllib`, no new packages. Model names editable; defaults `gemini-2.5-flash`, `gpt-5-mini` (verify against the providers' model lists on first real run).
- UI copy in Vietnamese.

## Review Focus

1. The model answers with the wrong number of lines, extra commentary, or code fences → parse what is valid JSON; a count mismatch translates that batch locally (no half-wrong mapping).
2. A key pasted with spaces / a trailing newline → stripped before saving and before use.
3. Offline or a slow provider during Live → each Live job waits at most 2.5 s, then local; the next 30 s go straight to local (no 2.5 s stall per sentence).
4. The daily limit is reached mid-session → local from then on, one notice, counter resets at local midnight.
5. An SDK / HTTP error whose text contains the key or the full request → the notice shows only the provider name and the error kind.

Each line has a test in the owning task (marked **RF1–RF5**).

---

### Task 1: Shared prompt / reply rules (fixtures + Python)

**Files:**
- Create: `shared/fixtures/llm/README.md`, `shared/fixtures/llm/prompt_*.json`, `shared/fixtures/llm/reply_*.json`
- Create: `windows/app/translate/llm_prompt.py`
- Test: `windows/tests/test_llm_prompt.py`

**Interfaces:**
- Produces: `build_messages(sentences: list[str], context: list[str], speaker: str | None, glossary: dict[str, str | None]) -> tuple[str, str]` (system, user); `parse_reply(text: str, n: int) -> list[str] | None`; `REPLY_SCHEMA: dict` (`{"type":"object","properties":{"translations":{"type":"array","items":{"type":"string"}}},"required":["translations"],"additionalProperties":false}`).

- [ ] **Step 1: Fixtures.** `prompt_*.json`: `{"input": {sentences, context, speaker, glossary}, "expected": {"system": "...", "user": "..."}}` — cases: plain (1 sentence, no context), context of 3 + speaker, glossary with keep (`null` target → "giữ nguyên") and map, context longer than 3 → only the last 3. `reply_*.json`: `{"text": "...", "n": int, "expected": [..] | null}` — cases: clean JSON; JSON inside ```json fences; text before/after the JSON object; wrong count → null; not JSON → null; empty strings in the array → null; a bare JSON array of strings → accepted.
  System prompt (exact copy, fixtures pin it): `Bạn dịch lời thoại và chữ trong game từ tiếng Anh sang tiếng Việt. Dịch tự nhiên, đúng giọng nhân vật, không thêm bớt ý. Giữ nguyên tên riêng. Trả về JSON {"translations": [...]}, mỗi câu đầu vào đúng một bản dịch, cùng thứ tự.`
  User message: sections `Thuật ngữ:` (one `- src → dst` / `- src (giữ nguyên)` per line, omitted when empty), `Câu trước (để hiểu ngữ cảnh, không dịch):` (omitted when empty), `Người nói: <name>` (omitted when None), then `Dịch các câu sau:` and the sentences as a JSON array.
- [ ] **Step 2:** `test_llm_prompt.py` loads every fixture and asserts equality. Run: `.venv/Scripts/python -m pytest -q windows/tests/test_llm_prompt.py` — Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `llm_prompt.py`. **RF1** is the reply fixtures.
- [ ] **Step 4:** Run — Expected: PASS.
- [ ] **Step 5:** Commit `feat(llm): shared prompt and reply rules`.

### Task 2: Profile `engine` field (Python + Kotlin)

**Files:**
- Modify: `windows/app/profiles.py`, `android/app-core/src/main/kotlin/dev/screentrans/core/profile/Profile.kt`, `shared/fixtures/profiles/*.json` + README
- Test: existing profile fixture tests (Python + Kotlin)

**Interfaces:**
- Produces: `Profile.engine: str = "local"` (JSON key `"engine"`), parsed like `ocr`: one of the five names, otherwise `"local"`.

- [ ] **Step 1:** Fixtures: every expected profile gets `"engine": "local"`; `full.json` input/expected `"engine": "claude"`; `broken_regions.json` input `"engine": "chatgpt"` → expected `"local"`. Run both suites — Expected: FAIL.
- [ ] **Step 2:** Implement in both languages. Run Python `windows/tests/test_profiles.py` and `gradlew :app-core:test` (JDK 17) — Expected: PASS.
- [ ] **Step 3:** Commit `feat(profile): per-game translation engine`.

### Task 3: Provider clients

**Files:**
- Create: `windows/app/translate/remote.py`
- Modify: `windows/requirements.txt` (+ `anthropic`)
- Test: `windows/tests/test_remote.py`

**Interfaces:**
- Produces: `class RemoteError(Exception)` with `.kind: Literal["auth", "quota", "timeout", "network", "server", "bad_reply"]` and a message without secrets; `class Client(Protocol): name: str; model: str; def complete(self, system: str, user: str, timeout_s: float) -> str` (returns the reply text); `make_client(engine: str, key: str, model: str, url: str = "") -> Client`; `DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "openai": "gpt-5-mini", "claude": "claude-opus-5-5", "kaggle": "server"}`.
- HTTP: `GeminiClient` POST `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, header `x-goog-api-key`, body `systemInstruction` + `contents` + `generationConfig.responseMimeType="application/json"`, text at `candidates[0].content.parts[0].text`. `OpenAiClient` POST `https://api.openai.com/v1/chat/completions`, `Authorization: Bearer`, `response_format={"type":"json_object"}`, text at `choices[0].message.content`. `KaggleClient` POST `{url}/translate` with `Authorization: Bearer <token>`, body `{"texts", "source_lang": "en", "context", "glossary"}`, returns `json.dumps({"translations": ...})` so parsing is shared. `ClaudeClient`: `anthropic.Anthropic(api_key=key, max_retries=0, timeout=timeout_s, http_client=...)`, `client.beta.messages.create(model, max_tokens=4096, system, messages, output_config={"effort": "low", "format": {"type": "json_schema", "schema": REPLY_SCHEMA}}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")`; `stop_reason == "refusal"` → `RemoteError("bad_reply")`; text from the first `text` block.
- Error mapping (all clients): 401/403 → auth; 429 → quota; 408/timeouts → timeout; other 5xx/529 → server; connection errors → network; unparsable body → bad_reply.

- [ ] **Step 1: Tests** with an injected transport: `urlopen` replaced via a constructor arg `opener` for the urllib clients; `httpx.MockTransport` passed as `http_client=httpx.Client(transport=...)` for Claude. Cases per client: success returns the text; 401 → auth; 429 → quota; 500 → server; timeout → timeout; garbage body → bad_reply. **RF5:** an error from a request carrying key `"sk-SECRET"` → `"sk-SECRET" not in str(err)`. **RF2:** `make_client("openai", "  sk-x\n", ...)` sends `Bearer sk-x`.
- [ ] **Step 2:** Run `windows/tests/test_remote.py` — Expected: FAIL.
- [ ] **Step 3:** Implement. Install `anthropic` into `.venv`.
- [ ] **Step 4:** Run — Expected: PASS.
- [ ] **Step 5:** Commit `feat(llm): Gemini / OpenAI / Claude / Kaggle clients`.

### Task 4: Encrypted keys + daily usage

**Files:**
- Create: `windows/app/secrets.py`, `windows/app/usage.py`
- Test: `windows/tests/test_secrets_usage.py`

**Interfaces:**
- Produces: `KeyStore(data_dir: Path)` with `get(engine) -> str`, `set(engine, key: str) -> None` (strips; empty removes), file `data_dir/keys.bin` = DPAPI(`CryptProtectData`, current user) of a JSON map; `Usage(data_dir: Path, clock=date.today)` with `used() -> int`, `add(chars: int) -> None`, `allows(chars: int, limit: int) -> bool`, file `data_dir/usage.json` `{"date": "YYYY-MM-DD", "chars": n}`.

- [ ] **Step 1: Tests:** round trip set/get; the file does not contain the key bytes; a corrupt `keys.bin` → `get` returns `""` (no crash); **RF4:** usage resets when the date changes; `allows` false past the limit.
- [ ] **Step 2:** Run — Expected: FAIL. **Step 3:** Implement (ctypes `crypt32`). **Step 4:** Run — Expected: PASS.
- [ ] **Step 5:** Commit `feat(llm): DPAPI key store and daily character usage`.

### Task 5: `LlmTranslator` + Pipeline hooks

**Files:**
- Create: `windows/app/translate/llm.py`
- Modify: `windows/app/pipeline.py`
- Test: `windows/tests/test_llm_translator.py`, `windows/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 `build_messages`, `parse_reply`; Task 3 `Client`, `RemoteError`; Task 4 `Usage`.
- Produces: `LlmTranslator(client: Client, local: Translator, usage: Usage, daily_limit: int, notify: Callable[[str], None], clock=time.monotonic)`; attributes `model_id = f"{engine}:{model}"`, `timeout_s: float` (worker sets it), `prefers_batch = True`; `translate(texts)` = `translate_ctx(texts, {})`; `translate_ctx(texts, glossary) -> list[str]`; `set_speaker(name: str | None)`; context = last 3 translated source sentences.
  Rules: blocked (auth) → local, no call; within 30 s of a failure → local, no call (**RF3**); usage would pass the limit → local + notice once per day (**RF4**); `RemoteError` → local + notice once per failure spell, text `"<Gemini|OpenAI|Claude|Kaggle>: <lý do> — dùng model trên máy."` (auth: `"... sai key hoặc hết quyền — mở Cài đặt để sửa."`); `parse_reply` None → local for that batch (**RF1**); success → usage.add(sum of len).
- Pipeline: `_translate_sentences` calls `translate_ctx(todo, glossary.terms_in(todo))` and skips protect/restore when the translator has it; `iter_sentences` with `prefers_batch` translates all pending sentences in one call, then yields one snapshot per sentence; the local model_id stays in `cache_ns` for local translations (a fallback result is not cached under the LLM namespace).
- New `Glossary.terms_in(texts: list[str]) -> dict[str, str | None]` in `windows/app/glossary.py`: only the entries that match inside `texts` (same matching as `protect`), keep → None — the common glossary is large, the prompt carries only what this batch uses. The Pipeline passes `glossary.terms_in(todo)`.

- [ ] **Step 1: Tests** with a fake client: context passed in the user message after two calls; failure → local result + one notice, second call within 30 s does not touch the client, after 31 s it does; auth → never called again until a new translator; limit; bad reply count → local; pipeline uses `translate_ctx` with the game glossary and does not insert placeholders; `iter_sentences` makes one client call for 3 sentences; fallback results not cached under `claude:` namespace.
- [ ] **Step 2:** Run — Expected: FAIL. **Step 3:** Implement. **Step 4:** Run full Windows suite — Expected: PASS.
- [ ] **Step 5:** Commit `feat(llm): LLM translator with context, fallback, limit`.

### Task 6: Worker — engine per game, timeouts per job

**Files:**
- Modify: `windows/app/gui/worker.py`
- Test: `windows/tests/test_worker.py`

**Interfaces:**
- Consumes: Task 5; `set_game` payload gains `"engine": str` and `"llm": {"model": str, "url": str, "daily_limit": int}`; key from `KeyStore`.
- Produces: worker keeps `self._local = pipeline.translator`; `_use_engine(engine, llm)` caches one `LlmTranslator` per (engine, model, url, key digest); `local` restores `_local`; before each job sets `timeout_s` = 2.5 (live_translate) or 6.0 (region / fullscreen); notices go to the existing `notice` signal; a missing key → local + notice `"Chưa nhập key cho <Provider> — dùng model trên máy."`.

- [ ] **Step 1: Tests** (monkeypatched `make_client`): engine switch applies to translate jobs; live job sees 2.5, region job 6.0; missing key → notice once, local result. **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS (full suite).
- [ ] **Step 5:** Commit `feat(llm): worker switches translation engine per game`.

### Task 7: Settings window + tray wiring

**Files:**
- Modify: `windows/app/gui/settings_dialog.py`, `windows/app/main.py`
- Test: `windows/tests/test_settings_dialog.py`, `windows/tests/test_app.py`

**Interfaces:**
- `SettingsValues` gains `engine: str = "local"`, `llm_models: dict[str, str]`, `kaggle_url: str = ""`, `daily_limit: int = 50000`, `keys: dict[str, str]` (only edited keys; never pre-filled — shown as `••••` placeholder when set).
- Dialog section "Dịch bằng" (per game): combo `Model trên máy` / `Gemini` / `OpenAI` / `Claude` / `Kaggle (server riêng)`; for the chosen provider: key field (password echo), model name, Kaggle URL; daily limit spin box; label `Đã dùng hôm nay: N ký tự`; warning label `Chữ trong game sẽ được gửi tới <Provider>.` shown when not local.
- Tray: saves `profile.engine`, non-secret LLM settings in `settings.json` (`llm.models`, `llm.kaggle_url`, `llm.daily_limit`), keys via `KeyStore`; resends `set_game` with `engine` + `llm`.

- [ ] **Step 1: Tests:** dialog shows the five engines; choosing Claude enables key/model and shows the warning; `values()` returns the stripped key only when edited; app saves engine to the profile, key to `KeyStore` (not `settings.json`), and the set_game payload carries `engine` and `llm` without the key. **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS (full suite).
- [ ] **Step 5:** Commit `feat(llm): settings for remote engines`.

### Task 8: Compare script, Kaggle server notebook, docs

**Files:**
- Modify: `windows/scripts/compare_engines.py` (engines `gemini`, `openai`, `claude`, `kaggle` via `--engine`, keys from `KeyStore`)
- Create: `training/kaggle_serve.ipynb` (vLLM + FastAPI + ngrok, `POST /translate`, `GET /health`, Bearer token printed at start; model `Qwen2.5-7B-Instruct-AWQ` default, prompt from the shared system text)
- Modify: `README.md` (feature line + how to enter a key), `AGENT.md` (tick 4c, 5a progress), `CHANGELOG.md`

- [ ] **Step 1:** `compare_engines.py --engine claude --no-samples --sentences x.txt` runs against a fake (`--dry-run` prints the prompts without network). Test: `windows/tests/test_compare_engines.py` (dry run output contains the system prompt).
- [ ] **Step 2:** Notebook: cells for install, model load, server, ngrok; not run in CI.
- [ ] **Step 3:** Docs. Full suite PASS. Commit `docs: phase 5a`.
