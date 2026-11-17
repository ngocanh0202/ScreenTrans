"""Run app.cli.main with a fake OCR + translator (used by test_cli via subprocess)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import cli  # noqa: E402
from app.cache import TranslationCache  # noqa: E402
from app.glossary import Glossary  # noqa: E402
from app.ocr.base import Line  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from fakes import FakeOcr, FakeTranslator  # noqa: E402

cli.build_pipeline = lambda config, args: Pipeline(
    FakeOcr([Line("Hello there.", 10, 10, 200, 30)]),
    FakeTranslator(lambda s: "Xin chào, Việt Nam!"),
    Glossary([]),
    TranslationCache(10, None),
)
sys.exit(cli.main(sys.argv[1:]))
