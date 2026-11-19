# Phase 5b-1 — Ngữ cảnh game cho LLM + chọn chữ thêm thuật ngữ (dùng chung + Windows) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM translations keep a game's voice — per-game notes, the user's corrections as examples, 10 previous lines with speakers saved per game — plus a pick-words term editor and the 5a minor fixes, on Windows; shared fixtures fix the rules for the Android port (5b-2).

**Architecture:** `build_messages` gains `notes` and `examples` and takes context as (speaker, text) pairs (shared fixtures v2). A `ContextStore` keeps each game's last 10 lines on disk; `LlmTranslator.set_game(game, notes, examples)` switches context. The worker passes notes and examples from the `set_game` payload. Term suggestions are a pure function with shared fixtures; the correction dialog shows the source words as selectable chips.

**Tech Stack:** Python 3.11, PySide6 (same as 5a).

**Spec:** `AGENT.md` §15 Phase 5, bullet "5b — Android + ngữ cảnh game cho LLM" (Windows / shared parts); 5a plan `docs/superpowers/plans/2026-11-19-phase5a-llm-windows.md` for the existing design.

## Global Constraints

- Prompt sections, in order, each omitted when empty, one blank line between: `Về game:` (notes), `Thuật ngữ:`, `Cách dịch người dùng đã sửa (làm theo giọng này):` (examples `- src → fixed`, at most 5, newest last), `Câu trước (để hiểu ngữ cảnh, không dịch):` (`- Speaker: text` or `- text`, at most 10), `Người nói: X`, `Dịch các câu sau:` + JSON array. System prompt unchanged.
- Context is per game, saved in `data_dir/llm_context/<game>.json`, never mixed between games; survives restarts.
- Examples = the game's latest overrides (user corrections), at most 5; a new correction is used from the next call.
- Notes: `Profile.llm_notes: str = ""` (JSON `llm_notes`, non-string → `""`), edited in the settings window per game.
- No prompt caching now (notes + examples are far below the minimum cacheable prefix); revisit if notes get long.
- Term editor: select one word or a run of words in a sentence's source → `Giữ nguyên` or `Dịch cố định` (type only the Vietnamese); added terms shown as removable chips; suggested names (shared rule) one click to keep. Output unchanged: `list[tuple[str, str | None]]`.
- 5a minors to fix here: default model not saved as a choice; delete a saved key; a wrong-key block clears when settings are applied again; Kaggle cache namespace includes the server host; Live keeps sentence-by-sentence display while falling back; fallback results cached under the local model; `usage.json` written atomically; a failing engine switch falls back to local with a notice; fullscreen sends a speaker only when the screen has exactly one name line; test for the daily-limit notice across midnight.

## Review Focus

1. A game id with characters invalid in file names (`:`, `\`, `?`) → the context file name is sanitized, no crash.
2. A corrupt / unreadable context file → starts empty, no crash, rewritten on the next success.
3. Notes or examples containing newlines / JSON-like text → passed verbatim inside their section, never break the sentence array at the end (fixture).
4. Selecting words across punctuation ("Constantine," at a comma) → the term is the words without trailing punctuation.
5. Switching game while a remote call is in flight → the late result is saved to the game it was asked for, not the new one.

---

### Task 1: Prompt v2 (fixtures + Python)

**Files:** Modify `shared/fixtures/llm/*` (+ README), `windows/app/translate/llm_prompt.py`, `windows/tests/test_llm_prompt.py`.

**Interfaces — Produces:** `build_messages(sentences: list[str], context: list[tuple[str | None, str]], speaker: str | None, glossary: dict[str, str | None], notes: str = "", examples: list[tuple[str, str]] = ()) -> tuple[str, str]`; `CONTEXT_MAX = 10`, `EXAMPLES_MAX = 5`.

- [ ] Fixtures: existing prompt fixtures move to the new `context` shape (`[[speaker|null, text], ...]`) with the same expected text; new `prompt_notes_examples.json` (all sections, notes with a newline, an example), `prompt_context_speakers.json` (mixed speakers / null, 12 lines → last 10). **RF3** in the notes fixture (notes contain `["x"]`).
- [ ] RED → implement → GREEN; commit `feat(llm): prompt v2 - game notes, correction examples, 10 lines with speakers`.

### Task 2: `Profile.llm_notes` (Python + Kotlin)

**Files:** `windows/app/profiles.py`, `android/.../profile/Profile.kt`, `shared/fixtures/profiles/*` + README.

- [ ] Fixtures: expected `"llm_notes": ""` everywhere; `full.json` a two-line note; `broken_regions.json` input `"llm_notes": 7` → `""`. RED both suites → implement → GREEN. Commit `feat(profile): per-game notes for LLM translation`.

### Task 3: Per-game context + LlmTranslator game switch + 5a translator minors

**Files:** Create `windows/app/translate/context_store.py`; modify `windows/app/translate/llm.py`, `windows/app/usage.py`, `windows/app/translate/remote.py` (Kaggle `model` = host); tests `windows/tests/test_llm_translator.py`, `windows/tests/test_secrets_usage.py`.

**Interfaces — Produces:** `ContextStore(data_dir)` with `load(game: str) -> list[tuple[str | None, str]]`, `save(game, lines)` (file `llm_context/<safe(game)>.json`, atomic; **RF1**, **RF2**); `LlmTranslator.set_game(game: str | None, notes: str, examples: list[tuple[str, str]])` (loads that game's context, clears the wrong-key block and back-off); `set_examples(examples)`; `available() -> bool` (not blocked, not backing off, under today's limit for ≥1 char); the context line stores the batch's speaker; a result is saved to the game captured when the call started (**RF5**). `Usage.add` writes tmp + replace. Daily-limit notice day comes from the usage clock (test across midnight). `make_client("kaggle", url=...)` → `client.model` = URL host, so `model_id` = `kaggle:<host>`.

- [ ] Tests first (context per game, persistence across instances, sanitized name, corrupt file, unblock on set_game, available(), late result goes to the old game, midnight notice, Kaggle model_id). RED → implement → GREEN. Commit `feat(llm): per-game saved context, notes and examples; translator fixes`.

### Task 4: Pipeline — fallback keeps Live progressive and cached; fullscreen speaker

**Files:** `windows/app/pipeline.py`; tests `windows/tests/test_llm_translator.py`.

- [ ] `iter_sentences` with `prefers_batch`: if `translator.available()` → one batch; if the batch comes back None or not available → per-sentence local loop (each sentence yielded as it is done). Fallback results cached under the local model's namespace (`f"{local.model_id}@{model_version}#{digest}"`) and looked up there first. `iter_segments` sets a speaker only when the screen has exactly one name paragraph, else None. `correct()` also calls `translator.set_examples(...)` when present (latest 5 overrides). Tests first; commit `fix(llm): fallback stays progressive and cached; fullscreen speaker`.

### Task 5: Worker — notes, examples, game; engine-switch failure

**Files:** `windows/app/gui/worker.py`, `windows/app/main.py` (payload `llm.notes`), tests `test_worker.py`, `test_app.py`.

- [ ] `set_game` payload `llm` gains `"notes"`; examples = the payload `overrides` (latest 5). `_use_engine` → `tr.set_game(game, notes, examples)` each time; any exception in `_use_engine` → local + notice `"Không bật được <Provider> — dùng model trên máy."`. Tests first; commit `feat(llm): worker passes game notes and corrections`.

### Task 6: Settings — notes, delete key, defaults not saved

**Files:** `windows/app/gui/settings_dialog.py`, `windows/app/main.py`, tests.

- [ ] `SettingsValues.llm_notes: str = ""`, `delete_keys: tuple[str, ...] = ()`; dialog: multi-line "Ghi chú game cho LLM" (placeholder with the Vertin example), button "Xóa key đã lưu" (enabled when the shown engine has a saved key) → adds to `delete_keys`; model names equal to the default are not returned in `llm_models`. Tray saves notes to the profile, deletes keys, resends set_game. Tests first; commit `feat(llm): settings - game notes, delete key`.

### Task 7: Term suggestions (shared) + pick-words term editor (Windows)

**Files:** Create `shared/fixtures/terms/` (+ README), `windows/app/text/terms.py`, `windows/app/gui/word_picker.py`; modify `windows/app/gui/correct_dialog.py`; tests `windows/tests/test_terms.py`, `windows/tests/test_correct_dialog.py`.

**Interfaces — Produces:** `words(sentence) -> list[str]` (tokens with surrounding punctuation stripped, **RF4**); `suggest_names(sentences: list[str], common: set[str], known: set[str]) -> list[str]` — runs of capitalized tokens with ≥1 uncommon token (a single sentence-initial common word is not a name), unique in first-seen order, minus `known`; fixtures pin cases ("Madam Constantine", "Ms. Z", "Druvis III", sentence-initial "Where", already-known). `WordPicker(sentence)` — words as checkable chips; click selects one word, shift-click or drag extends to a contiguous run; `selection() -> str`. CorrectDialog: per sentence a picker; bar `[Giữ nguyên] [Dịch cố định: ____ ]`; chips of added terms with ✕; suggestion chips (+); `parsed_terms()` returns the chips (the old text box removed).

- [ ] Fixtures + tests first (suggestions, selection by click / shift-click / drag via qtbot, keep and fixed terms, remove chip). RED → implement → GREEN. Commit `feat(correct): pick words to add glossary terms, name suggestions`.

### Task 8: Docs

- [ ] README (ghi chú game, chọn chữ), CHANGELOG, AGENT.md 5b progress. Full suite PASS. Commit `docs: phase 5b-1`.
