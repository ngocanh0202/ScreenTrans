"""Pair filters for fine-tuning data (Phase 6)."""
from training.filters import dedupe, keep_pair, normalize, split_heldout


def test_normalize_collapses_space_and_strips_bom():
    assert normalize("﻿  Hello \t there  \r") == "Hello there"


def test_real_short_dialogue_is_kept():  # RF2
    for en, vi in [("Hi.", "Chào."), ("No!", "Không!"), ("Where are you going?", "Bạn đi đâu vậy?"),
                   ("Druvis III is an Arcanist.", "Druvis III là một Thuật sĩ.")]:
        assert keep_pair(en, vi), (en, vi)


def test_junk_is_dropped():  # RF2
    bad = [("", "Chào."), ("Hello", ""), ("See https://x.com now", "Xem https://x.com ngay"),
           ("12345", "12345"), ("This is a fairly long English sentence here.", "This is a fairly long English sentence here."),
           ("Hello there my friend how are you", "Xin chào"),            # ratio far too small
           ("Yes.", "Vâng, tôi hoàn toàn đồng ý với tất cả những gì bạn vừa nói ra trong buổi họp sáng nay."),
           ("I like this book very much", "I like this livre beaucoup ici"),   # no Vietnamese at all
           ("word " * 250, "từ " * 250)]
    for en, vi in bad:
        assert not keep_pair(en, vi), (en[:30], vi[:30])


def test_dedupe_by_casefolded_source_and_heldout_removed():  # RF3
    pairs = [("Hello.", "Chào."), ("hello. ", "Xin chào."), ("Bye.", "Tạm biệt."), ("Go now.", "Đi ngay.")]
    assert dedupe(pairs) == [("Hello.", "Chào."), ("Bye.", "Tạm biệt."), ("Go now.", "Đi ngay.")]
    assert split_heldout(dedupe(pairs), {"go now."}) == [("Hello.", "Chào."), ("Bye.", "Tạm biệt.")]
