"""Export a Marian model to ONNX int8 for Android (encoder + merged decoder with KV-cache)."""
import shutil
import tempfile
from pathlib import Path

from models.registry import MODELS
from models.sp_export import export_sp

OUT = Path(__file__).parent / "out"


def export_onnx(key: str, hf_id: str | None = None) -> Path:
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from optimum.exporters.onnx import main_export
    from transformers import AutoTokenizer

    from models.registry import spec_for

    spec = spec_for(key, hf_id)
    if spec.kind != "marian":
        raise ValueError("Android ONNX export is only defined for Marian models in Phase 0")
    out_dir = OUT / f"{key}-onnx"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    from optimum.onnx import merge_decoders

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        # no_post_process: skip optimum's own merge; quantize_dynamic cannot reach weights
        # inside the merged model's If-branches, so quantize the two decoders first, then merge.
        main_export(spec.hf_id, output=tmp, task="text2text-generation-with-past", no_post_process=True)
        quantize_dynamic(str(t / "encoder_model.onnx"), str(out_dir / "encoder_model.onnx"), weight_type=QuantType.QInt8, per_channel=True)
        for name in ("decoder_model.onnx", "decoder_with_past_model.onnx"):
            quantize_dynamic(str(t / name), str(t / f"q_{name}"), weight_type=QuantType.QInt8, per_channel=True)
        merge_decoders(
            str(t / "q_decoder_model.onnx"),
            str(t / "q_decoder_with_past_model.onnx"),
            save_path=str(out_dir / "decoder_model_merged.onnx"),
            strict=False,
        )
        for name in ("config.json", "generation_config.json"):
            if (Path(tmp) / name).exists():
                shutil.copy(Path(tmp) / name, out_dir / name)
    AutoTokenizer.from_pretrained(spec.hf_id).save_pretrained(str(out_dir))
    export_sp(out_dir / "source.spm", out_dir / "sp_source.json")
    return out_dir
