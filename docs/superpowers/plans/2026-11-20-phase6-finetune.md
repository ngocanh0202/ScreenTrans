# Phase 6 — Fine-tune `opus-mt-en-vi` on open data (+ a private distillation tool) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything needed to fine-tune `Helsinki-NLP/opus-mt-en-vi` on openly licensed EN–VI data on Kaggle, evaluate it against the base model, and plug the result into the existing export pipeline — plus a tool for users to build a private model from LLM-generated data with their own key.

**Architecture:** Pure, tested Python in `training/` (corpus catalogue + OPUS download/reader, pair filters, dataset builder, distillation tool) used by a Kaggle notebook that clones the repo, builds the dataset, trains with `Seq2SeqTrainer`, evaluates (FLORES-200 devtest chrF/BLEU + game sentences side by side) and saves / pushes the model. `models/export.py` gains `--hf-id` so a fine-tuned checkpoint exports to CT2 / ONNX like the shipped models.

**Tech Stack:** Python 3.11 stdlib (zipfile, urllib) for the tested parts; transformers / datasets / sacrebleu / sentencepiece on Kaggle only.

**Spec:** `AGENT.md` §15 Phase 6; licenses: `docs/superpowers/reports/2026-11-20-en-vi-licenses.md`.

## Global Constraints
- Public model data = only: ALT, Tatoeba, translatewiki, ELRC_2922 (attribution), NLLB-OPUS and ParaCrawl-Bonus subsets (filtered). Every corpus entry carries its license + attribution; the notebook writes `DATA_LICENSES.md` next to the model. CC-BY-SA corpora are off unless `--allow-sa` (then the model card says CC-BY-SA 4.0). Never PhoMT, TED/IWSLT, QED, MTet, OpenSubtitles.
- LLM-generated data never enters the repo or the public model; the distillation tool writes to a user folder outside git.
- No large local downloads: corpora are downloaded on Kaggle (tests use tiny fake zips).
- Model output name: `screentrans-en-vi` (Apache-2.0 + attribution to Helsinki-NLP / OPUS-MT and data sources).

## Review Focus
1. OPUS moses zips with mismatched line counts / BOM / CRLF → pairs stay aligned, bad files are skipped with a message.
2. Filters keep real short dialogue ("Hi.", "No!", "Xin chào.") while dropping junk (URLs, numbers only, wrong language, extreme length ratios).
3. Deduplication is by normalized source, and the held-out eval sentences never appear in training.
4. The distillation tool never writes the key anywhere, resumes after interruption, and stops at the character budget.
5. A model exported with `--hf-id` gets a correct `screentrans_model.json` so the app loads it.

### Task 1: Pair filters — `training/filters.py` (+ `training/tests/test_filters.py`)
`normalize(s)`, `keep_pair(en, vi) -> bool` (both non-empty after normalize; 1–200 words; char length ratio vi/en in [0.5, 3.0]; no URL/e-mail; en has ≥1 ASCII letter; vi has a Vietnamese letter or diacritic when it has ≥4 words; not identical en==vi when ≥3 words), `dedupe(pairs)` (by casefolded en), `split_heldout(pairs, heldout_en)` removes eval sentences. Tests first.

### Task 2: Corpora — `training/corpora.py` (+ tests)
`CORPORA` list: name, OPUS id, version, license, attribution, max_pairs default, `share_alike` flag; `opus_url(c)` (`https://object.pouta.csc.fi/OPUS-{id}/{version}/moses/en-vi.txt.zip`); `read_moses_zip(path) -> Iterator[(en, vi)]` (pairs the `.en` / `.vi` members line by line, strips BOM/CRLF, stops with a warning on a count mismatch); `build(out_dir, corpora, max_pairs, heldout)` -> `train.tsv`, `dev.tsv` (1 % up to 2 000), `DATA_LICENSES.md`, `stats.json`. Download injected (tests use fake zips).

### Task 3: Export a fine-tuned model — `models/export.py --hf-id`
Register `screentrans-en-vi` (marian) in `models/registry.py` with an overridable `hf_id`; `export.py ct2|onnx screentrans-en-vi --hf-id <repo or folder>`; meta file names the key. Test with the existing meta tests.

### Task 4: Kaggle notebook — `training/kaggle_finetune.ipynb` (+ `training/README.md`)
Cells: settings (corpora, max pairs, epochs, push target); install; clone repo; build dataset (Task 2); load base model; tokenize; `Seq2SeqTrainer` (fp16, lr 5e-5, batch 64, eval each N steps, keep best by chrF); evaluate base vs fine-tuned on FLORES-200 devtest (chrF + BLEU, eval only) and print game sample sentences side by side; save to `/kaggle/working/screentrans-en-vi` with model card + `DATA_LICENSES.md`; optional push to Hugging Face (secret `HF_TOKEN`). Cells compile; not run in CI.

### Task 5: Private distillation tool — `training/distill_data.py` (+ tests)
`--engine gemini|openai|claude|kaggle --key-from settings|env --sentences FILE... --out DIR --limit N --budget-chars N`: batches of 20 sentences through the app's prompt + remote clients (`build_messages`, `parse_reply`, `make_client`), appends `distilled.tsv`, resumes (skips done sentences), prints a cost estimate before starting (`--yes` to proceed), stops at the budget, never writes the key. Adds the user's `corrections.jsonl` pairs with `--with-corrections`. Tests with a fake client.

### Task 8: Docs — README (Phase 6 how-to), AGENT.md progress, CHANGELOG.
