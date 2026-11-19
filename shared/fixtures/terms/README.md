# Term picking fixtures (Phase 5b)

Python (`windows/app/text/terms.py`) is the reference; the Kotlin port (5b-2) must pass the same files.
Common words: `shared/glossary/common_words_en.txt` (lowercase, one per line).

Tokens: the sentence split on whitespace. A token's *core* is the token with leading / trailing
punctuation removed (`.,!?;:"'()[]…“”‘’—-`). Abbreviations: `Mr Mrs Ms Dr St Mt Jr Sr` (core, any case).

`span.json` — `span(sentence, from, to)`: tokens `from..to` (inclusive) joined with one space, then leading
punctuation of the first and trailing punctuation of the last removed. A trailing `.` is kept only when the
last core is an abbreviation (`Ms.`).

`suggest.json` — `suggest_names(sentences, common, known)`:
- A *run* is consecutive tokens whose core starts with an uppercase letter (core `I` never counts). A run
  ends after a token ending in `, ; : ! ?` or `…`, or in `.` unless its core is an abbreviation.
- At the start of a sentence, leading tokens whose core is a common word (and not an abbreviation) are
  dropped from the run.
- A run is a name when at least one core is not a common word (case-insensitive).
- The name is `span` of the run. Unique (case-insensitive), first-seen order, minus `known` (case-insensitive).
