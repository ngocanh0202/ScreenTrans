"""Regenerate common_words_en.txt (top English words) used by ProperNounTracker.

Usage: .venv\Scripts\python shared/glossary/make_common_words.py
"""
from pathlib import Path

from wordfreq import top_n_list

N = 5000

if __name__ == "__main__":
    out = Path(__file__).with_name("common_words_en.txt")
    out.write_text("\n".join(top_n_list("en", N)) + "\n", encoding="utf-8")
    print(f"Wrote {N} words to {out}")
