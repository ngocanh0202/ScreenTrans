"""Translate the English text in an image or a screen region to Vietnamese.

Usage:
  python -m app.cli --image anh.png
  python -m app.cli --screen x,y,w,h
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from app.capture import capture_region, parse_region
from app.config import Config, ConfigError, load_config
from app import factory
from app.models import ModelDownloadError
from app.ocr.base import OcrUnavailable
from app.paths import default_config_path
from app.pipeline import Pipeline
from app.translate.base import ModelNotFound

DEFAULT_CONFIG = default_config_path()
NO_TEXT = "(không tìm thấy chữ)"


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ArgError(message)


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=Path, help="ảnh cần dịch")
    src.add_argument("--screen", help="vùng màn hình x,y,w,h (pixel vật lý)")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--model-dir", type=Path, help="thư mục model CTranslate2 đã export")
    p.add_argument("--glossary", type=Path, action="append", default=[], help="bảng thuật ngữ game (lặp được)")
    p.add_argument("--show-source", action="store_true", help="in kèm câu gốc tiếng Anh")
    p.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    p.add_argument("--timings", action="store_true", help="in thời gian từng bước ra stderr")
    return p


def _cli_progress(done: int, total: int) -> None:
    print(f"\rĐang tải model: {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="", file=sys.stderr, flush=True)


def build_pipeline(config: Config, args: argparse.Namespace) -> Pipeline:
    return factory.build_pipeline(config, args.model_dir, args.glossary, progress=_cli_progress)


def _print_result(result, args) -> None:
    if args.json:
        data = {
            "segments": [
                {"kind": s.kind, "source": s.source, "translation": s.translation, "box": list(s.box)}
                for s in result.segments
            ],
            "timings_ms": {k: round(v, 1) for k, v in result.timings_ms.items()},
        }
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return
    if not result.segments:
        print(NO_TEXT)
        return
    for s in result.segments:
        if s.kind == "name":
            print(f"[{s.source}]")
        else:
            if args.show_source:
                print(f"EN: {s.source}")
            print(s.translation)
            print()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        args = _parser().parse_args(argv)
        img = Image.open(args.image) if args.image else capture_region(*parse_region(args.screen))
        config = load_config(args.config)
    except (_ArgError, ValueError, ConfigError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    try:
        pipeline = build_pipeline(config, args)
        result = pipeline.run(img)
    except (ModelNotFound, ModelDownloadError) as e:
        print(str(e), file=sys.stderr)
        return 2
    except OcrUnavailable as e:
        print(str(e), file=sys.stderr)
        return 3
    _print_result(result, args)
    if args.timings:
        print(" ".join(f"{k}={v:.0f}ms" for k, v in result.timings_ms.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
