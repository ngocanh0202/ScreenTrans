"""Dump a SentencePiece model to JSON so the Kotlin tokenizer can load it without native code."""
import json
from pathlib import Path

# SentencePiece piece types (sentencepiece_model.proto)
NORMAL, UNKNOWN, CONTROL, USER_DEFINED, UNUSED, BYTE = 1, 2, 3, 4, 5, 6


def export_sp(spm_path: Path, out: Path) -> None:
    import sentencepiece as spm

    sp = spm.SentencePieceProcessor(model_file=str(spm_path))
    pieces = []
    for i in range(sp.get_piece_size()):
        if sp.is_unknown(i):
            kind = UNKNOWN
        elif sp.is_control(i):
            kind = CONTROL
        elif sp.is_unused(i):
            kind = UNUSED
        elif sp.is_byte(i):
            kind = BYTE
        else:
            kind = NORMAL
        pieces.append([sp.id_to_piece(i), sp.get_score(i), kind])
    data = {"pieces": pieces, "unk_id": sp.unk_id(), "normalizer": "nmt_nfkc"}
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
