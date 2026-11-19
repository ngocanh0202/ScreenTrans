# LLM prompt / reply fixtures (Phase 5)

Python (`windows/app/translate/llm_prompt.py`) is the reference; the Kotlin port (5b) must pass the same files.

`prompt_*.json`: `input` = `{sentences, context, speaker, glossary, notes?, examples?}` → `expected` = `{system, user}`.
- `context`: `[[speaker | null, text], ...]`; `notes`: string (default `""`); `examples`: `[[source, user's fix], ...]` (default `[]`).
- `system`: fixed text (see any fixture).
- `user`: sections separated by one blank line, each omitted when empty, in this order:
  1. `Về game:` then the notes verbatim;
  2. `Thuật ngữ:` then one line per glossary entry, in the given order: `- src → dst`, or `- src (giữ nguyên)` when the target is `null`;
  3. `Cách dịch người dùng đã sửa (làm theo giọng này):` then `- src → fixed` for the **last 5** examples;
  4. `Câu trước (để hiểu ngữ cảnh, không dịch):` then `- Speaker: text` (or `- text` without a speaker) for the **last 10** context lines;
  5. `Người nói: <speaker>`;
  6. `Dịch các câu sau:` then the sentences as one JSON array (UTF-8, not escaped, `", "` between items).

`reply_*.json`: `text` (the model's reply) + `n` (sentences sent) → `expected` (list) or `null` (unusable: translate locally).
- Code fences and text around the JSON are ignored: parse from the first `{` or `[`.
- An object must have `translations`; a bare array of strings is accepted.
- Exactly `n` items, each a string non-empty after trimming; items are trimmed.
