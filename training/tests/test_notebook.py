"""The Kaggle notebook is generated from training/make_finetune_notebook.py and its code cells compile."""
import json
from pathlib import Path

NB = Path(__file__).resolve().parents[1] / "kaggle_finetune.ipynb"


def test_notebook_is_up_to_date_and_cells_compile():
    from training.make_finetune_notebook import CELLS

    nb = json.loads(NB.read_text(encoding="utf-8"))
    assert nb["cells"] == CELLS  # regenerate with: python training/make_finetune_notebook.py
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            src = "".join(cell["source"])
            compile("\n".join("pass" if l.lstrip().startswith("!") else l for l in src.splitlines()), "cell", "exec")


def test_notebook_uses_only_catalogued_open_corpora():
    from training.corpora import CORPORA

    src = "".join("".join(c["source"]) for c in json.loads(NB.read_text(encoding="utf-8"))["cells"])
    names = {c.name for c in CORPORA}
    assert all(n in names for n in ["ALT", "Tatoeba", "translatewiki", "ELRC_2922", "NLLB", "ParaCrawl-Bonus"])
    for banned in ("PhoMT", "TED2020", "QED", "OpenSubtitles"):
        assert banned not in src


def test_publishing_to_the_apps_is_guarded():
    """Only a model better than the base one, never with private LLM data or share-alike data, needs a token."""
    from training.make_finetune_notebook import CELLS

    cell = next("".join(c["source"]) for c in CELLS if "publish to the apps" in "".join(c["source"]))
    order = [cell.index(s) for s in ("elif EXTRA_TSV:", "elif ALLOW_SHARE_ALIKE:", "elif not better:", "elif token:")]
    assert order == sorted(order)
    assert '"--only", "screentrans-en-vi"' in cell and '"--merge-from", MANIFEST' in cell
