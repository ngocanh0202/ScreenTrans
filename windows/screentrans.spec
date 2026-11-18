# PyInstaller spec for the ScreenTrans tray app (onedir, no console).
# Build from the repo root:  .venv\Scripts\pyinstaller windows\screentrans.spec --noconfirm
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is provided by PyInstaller)

datas = [
    (str(ROOT / "shared" / "glossary"), "shared/glossary"),
    (str(ROOT / "windows" / "config.yaml"), "windows"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE.md"), "."),
]
hiddenimports = (
    collect_submodules("winrt")
    + collect_submodules("transformers.models.marian")
    + collect_submodules("transformers.models.mbart")
    + ["sentencepiece", "sacremoses"]
)
# Dev-only / unused heavy packages that transformers may try to pull in.
excludes = ["torch", "torchvision", "tensorflow", "jax", "flax", "onnx", "onnxruntime", "optimum",
            "sacrebleu", "matplotlib", "IPython", "notebook", "pytest", "rapidocr_onnxruntime"]

a = Analysis(  # noqa: F821
    [str(ROOT / "windows" / "app" / "__main__.py")],
    pathex=[str(ROOT / "windows")],
    binaries=collect_dynamic_libs("ctranslate2"),
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScreenTrans",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ScreenTrans", upx=False)  # noqa: F821
