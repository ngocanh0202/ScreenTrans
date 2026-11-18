"""Build the translation Pipeline from config (shared by the CLI and the tray app)."""
from pathlib import Path
from typing import Callable

from app.cache import TranslationCache
from app.config import Config
from app.datalog import CorrectionLogger, PairLogger
from app.glossary import COMMON_GLOSSARY, Glossary, ProperNounTracker, load_common_words
from app.models import ensure_model
from app.ocr.windows_ocr import WindowsOcr
from app.pipeline import Pipeline
from app.translate.ct2 import Ct2Translator


def resolve_model_dir(config: Config, model_dir: Path | None,
                      progress: Callable[[int, int], None] | None = None) -> Path:
    model_dir = model_dir or (Path(config.translator.model_dir) if config.translator.model_dir else None)
    if model_dir is not None:
        return model_dir
    return ensure_model(config.translator.model, config.models.manifest_url, Path(config.paths.data_dir),
                        progress=progress)


def build_pipeline(config: Config, model_dir: Path | None, glossaries: list[Path],
                   progress: Callable[[int, int], None] | None = None) -> Pipeline:
    data_dir = Path(config.paths.data_dir)
    resolved = Path(resolve_model_dir(config, model_dir, progress))
    translator = Ct2Translator(
        resolved, beam_size=config.translator.beam_size,
        intra_threads=config.translator.intra_threads,
    )
    glossary = Glossary.load(*glossaries, COMMON_GLOSSARY)  # game glossaries win over the common one
    cache = TranslationCache(config.cache.max_items, data_dir / "cache.sqlite" if config.cache.persist else None)
    return Pipeline(
        WindowsOcr(), translator, glossary, cache,
        tracker=ProperNounTracker(load_common_words()),
        pair_logger=PairLogger(data_dir / "translations.jsonl", config.logging.save_pairs),
        corrections=CorrectionLogger(data_dir / "corrections.jsonl", config.logging.save_corrections),
        model_version=resolved.name,  # data_dir/models/<id>/<version>, or the folder given with --model-dir
    )
