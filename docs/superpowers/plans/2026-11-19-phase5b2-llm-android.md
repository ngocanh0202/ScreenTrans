# Phase 5b-2 — Dịch bằng LLM trên Android (port 5a + 5b-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Android gets the Windows remote-LLM translation as it is after 5a + 5b-1 — Gemini / OpenAI / Claude / Kaggle per game, context / notes / examples, fallback to the on-device model, encrypted keys, daily limit, settings — and the pick-words term editor.

**Architecture:** Pure rules in `text-core` (prompt, reply parsing, term picking, Pipeline remote hooks) pass the same shared fixtures as Python. Network clients, `LlmTranslator`, context and usage stores live in `app-core` (JVM, testable with fake transports). The `app` module adds the Android Keystore key store, engine wiring in `TranslationEngine` / `AppEngine`, the settings section and the correction view.

**Tech Stack:** Kotlin, Gson (already used), `java.net.HttpURLConnection`, `com.anthropic:anthropic-java:3.3.0` (Claude), `okhttp3:mockwebserver` (tests only), Android Keystore (AES/GCM).

**Spec:** `AGENT.md` §15 Phase 5 bullet 5b; Windows reference: `docs/superpowers/plans/2026-11-19-phase5a-llm-windows.md`, `docs/superpowers/plans/2026-11-19-phase5b1-llm-context-windows.md` and the Python code they produced (`windows/app/translate/{llm_prompt,remote,llm,context_store}.py`, `windows/app/text/terms.py`, `windows/app/pipeline.py`).

## Global Constraints

- Same behaviour as Windows: every rule in `shared/fixtures/llm` and `shared/fixtures/terms` passes in Kotlin; timeouts 2.5 s Live / 6 s one-shot as one overall deadline; back-off 30 s; wrong key (401/403, Gemini 400 API_KEY_INVALID) blocks until `setGame` again; characters counted before the call; unusable reply → that batch locally; Live progressive while falling back; fallback results cached under the local model; context 10 lines per game on disk; examples = latest 5 overrides; fullscreen speaker only with one name line.
- Keys: Android Keystore (AES/GCM key, ciphertext in private prefs); never in logs (`Lưu nhật ký Live`), toasts, profiles or exceptions shown. Inner whitespace / zero-width characters removed.
- Gemini `thinkingBudget: 0`, OpenAI `reasoning_effort: "minimal"`, Claude `effort: "low"` + JSON schema output + server-side fallbacks `"default"`; default models as Windows (`gemini-2.5-flash`, `gpt-5-mini`, `claude-opus-5-5`); Kaggle model id = URL host.
- Android `app` module builds only on CI; everything testable goes in `text-core` / `app-core` with JVM tests (JDK 17: `JAVA_HOME=~/.jdks/jdk-17.0.21+9`).
- UI copy Vietnamese, same wording as Windows.

## Review Focus

1. The anthropic-java client on Android (OkHttp, Jackson): must not be created on the main thread and must not crash the app when the SDK fails to initialize → engine falls back to local with a notice.
2. Network on the main thread → `NetworkOnMainThreadException`: every remote call runs on the engine dispatcher.
3. Keystore unavailable / key invalidated (device lock changed) → saved keys read as empty, user asked to enter again, no crash.
4. Rotation / process death while a call is in flight → no leaked threads writing to a destroyed view.
5. The correction view on small screens: word chips wrap, the selection bar stays reachable.

---

### Task 1: `text-core` prompt + reply (`LlmPrompt.kt`)
- `buildMessages(sentences, context: List<Pair<String?, String>>, speaker, glossary: Map<String, String?>, notes = "", examples: List<Pair<String,String>> = emptyList()): Pair<String,String>`, `parseReply(text, n): List<String>?`, `REPLY_SCHEMA_JSON`. Test: load every `shared/fixtures/llm/*.json`. RED → GREEN → commit.

### Task 2: `text-core` term picking (`Terms.kt`)
- `tokens`, `span(tokens, from, to)`, `suggestNames(sentences, common, known)`; common words loaded from `shared/glossary/common_words_en.txt` in tests (the app bundles it already for ProperNounTracker — check, else add to assets). Test: `shared/fixtures/terms/*.json`. Commit.

### Task 3: `text-core` Pipeline remote hooks
- `interface RemoteEngine { val modelId; val local: SentenceTranslator; val localModelId; fun translateCtx(texts, glossary): List<String>?; fun available(): Boolean; fun setSpeaker(name: String?); fun setExamples(ex: List<Pair<String,String>>) }`; `Pipeline.setEngine(engine: RemoteEngine?)`; `Glossary.termsIn(texts)`; `examples()`; same branching as Python `_translate_sentences` / `iter_sentences` / `iter_segments` / `correct`. Tests ported from `windows/tests/test_llm_translator.py` (pipeline part) with a fake engine. Commit.

### Task 4: `app-core` remote clients
- `RemoteError(kind)`, `interface LlmClient { val name; val model; fun complete(system, user, timeoutMs): String }`, `makeClient(engine, key, model, url, transport)`. Gemini / OpenAI / Kaggle over `HttpURLConnection` behind `fun interface HttpTransport { fun post(url, headers, body, timeoutMs): Pair<Int, ByteArray> }`; Claude via anthropic-java (`AnthropicOkHttpClient.builder().apiKey(key).baseUrl(...).maxRetries(0)`, beta messages, output config effort low + JSON schema, `fallbacks` via additional body property + beta header). Tests: fake transport (shapes, 401/403/429/5xx/timeout/garbage, Gemini 400 invalid key, key never in messages, key cleaning) and MockWebServer for Claude. Commit.

### Task 5: `app-core` LlmTranslator + stores
- `LlmTranslator(engine, client, local, localModelId, usage: UsageStore, dailyLimit, notify, clock, contexts: ContextStore?) : RemoteEngine` with `setGame(game, notes, examples)`, deadline via a cached thread pool + `Future.get(timeout)`. `UsageStore(dir, today)` and `ContextStore(dir)` (JSON files, atomic writes, sanitized names). Tests ported from Python (context per game, late reply to its game, back-off, auth block, limit + midnight, bad reply, any exception hidden, deadline caps the call, chars counted before). Commit.

### Task 6: `app` — engine wiring and key store
- `KeyVault` (Android Keystore AES/GCM, prefs `llm_keys`); `EngineControl.SetGame` gains `engine`, `llm` (model, url, dailyLimit, notes); `TranslationEngine.run` sets timeout per job (Live 2500 / one-shot 6000 ms) and calls the bundle's `useEngine`; `AppEngine` builds `LlmTranslator`s (cached by engine/model/url/key hash), notices → toast; failures → local + notice. Controller sends the profile's engine / notes / overrides. CI build. Commit.

### Task 7: `app` — settings and correction view
- SettingsPanel "Dịch bằng" (grid of 5 engines, key field with "đã lưu" placeholder + "Xóa key", model name, Kaggle URL, daily limit, used today, privacy warning, game notes); saved: engine + notes in the profile, keys in `KeyVault`, the rest in prefs (defaults not saved). CorrectView: words as chips (tap / tap another to extend / drag), bar "Giữ nguyên" / "Dịch cố định", term chips with ✕, suggested names. CI build. Commit.

### Task 8: Docs — README (Android column), CHANGELOG, AGENT.md (5b done). Commit; merge after CI green.
