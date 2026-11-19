# LLM prompt / reply fixtures (Phase 5)

Python (`windows/app/translate/llm_prompt.py`) is the reference; the Kotlin port (5b) must pass the same files.

`prompt_*.json`: `input` = `{sentences, context, speaker, glossary}` → `expected` = `{system, user}`.
- `system`: fixed text (see any fixture).
- `user`: sections separated by one blank line, each omitted when empty, in this order:
  1. `Thuật ngữ:` then one line per glossary entry, in the given order: `- src → dst`, or `- src (giữ nguyên)` when the target is `null`;
  2. `Câu trước (để hiểu ngữ cảnh, không dịch):` then `- sentence` for the **last 3** context sentences;
  3. `Người nói: <speaker>`;
  4. `Dịch các câu sau:` then the sentences as one JSON array (UTF-8, not escaped, `", "` between items).

`reply_*.json`: `text` (the model's reply) + `n` (sentences sent) → `expected` (list) or `null` (unusable: translate locally).
- Code fences and text around the JSON are ignored: parse from the first `{` or `[`.
- An object must have `translations`; a bare array of strings is accepted.
- Exactly `n` items, each a string non-empty after trimming; items are trimmed.
