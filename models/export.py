"""Export translation models for the apps.

Usage:
  python -m models.export ct2 <key>    -> models/out/<key>-ct2/   (Windows, CTranslate2 int8)
  python -m models.export onnx <key>   -> models/out/<key>-onnx/  (Android, ONNX int8)
"""
import argparse
import json
from pathlib import Path

from models.registry import MODELS

OUT = Path(__file__).parent / "out"


META_FILE = "screentrans_model.json"


def model_meta(key: str, fmt: str) -> dict:
    """Metadata the apps read next to the model files."""
    spec = MODELS[key]
    return {"id": key, "kind": spec.kind, "format": fmt, "src_lang": spec.src_lang, "tgt_prefix": spec.tgt_prefix}


def write_meta(out_dir: Path, key: str, fmt: str) -> None:
    (out_dir / META_FILE).write_text(json.dumps(model_meta(key, fmt), indent=1) + "\n", encoding="utf-8")


def export_ct2(key: str) -> Path:
    import ctranslate2
    from models.verify import load_tokenizer

    spec = MODELS[key]
    out_dir = OUT / f"{key}-ct2"
    ctranslate2.converters.TransformersConverter(spec.hf_id).convert(
        str(out_dir), quantization="int8", force=True
    )
    load_tokenizer(spec).save_pretrained(str(out_dir))
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("backend", choices=["ct2", "onnx"])
    ap.add_argument("key", choices=list(MODELS))
    args = ap.parse_args()
    if args.backend == "ct2":
        out = export_ct2(args.key)
    else:
        from models.onnx_export import export_onnx

        out = export_onnx(args.key)
    write_meta(out, args.key, args.backend)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"Exported {args.key} -> {out} ({size:.0f} MB)")


if __name__ == "__main__":
    main()
