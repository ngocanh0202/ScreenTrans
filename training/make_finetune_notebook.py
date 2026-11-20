"""Writes training/kaggle_finetune.ipynb (Phase 6). Edit the cells here, then run:

    .venv\\Scripts\\python training/make_finetune_notebook.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "kaggle_finetune.ipynb"


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


CELLS = [
    md('''
# ScreenTrans — fine-tune `opus-mt-en-vi` on open data (Phase 6)

Fine-tunes [Helsinki-NLP/opus-mt-en-vi](https://huggingface.co/Helsinki-NLP/opus-mt-en-vi) (75M, same speed as the
model ScreenTrans ships) on **openly licensed** English–Vietnamese corpora only (see `DATA_LICENSES.md` written next to
the model and `docs/superpowers/reports/2026-11-20-en-vi-licenses.md` in the repo).

1. Notebook settings: **Accelerator = GPU T4 x2 or P100**, **Internet = On**.
2. Add-ons → Secrets → `HF_TOKEN` (a **write** token): the notebook then publishes the model to the app's model
   repo `APP_MODELS_REPO` (the apps show "Có bản mới") — only when it scores better than the base model, never
   with private LLM data. Optional: `PUSH_TO` for the plain Hugging Face model.
3. **Run all.** Downloading + filtering takes ~20–40 min (NLLB is large), training a few hours. The result is in
   `/kaggle/working/screentrans-en-vi` (and `screentrans-en-vi.zip` to download).
4. On your PC: `python -m models.export ct2 screentrans-en-vi --hf-id <folder or repo>` (Windows) and `onnx` (Android).

A private model from LLM-generated data: run `training/distill_data.py` on your PC with your own key, upload
`distilled.tsv` as a Kaggle Dataset and set `EXTRA_TSV` below. **Do not publish that model** (provider terms).
'''),
    code('''
# ---- settings ----
REPO = "https://github.com/ngocanh0202/ScreenTrans"
CORPORA_ON = ["ALT", "Tatoeba", "translatewiki", "ELRC_2922", "NLLB", "ParaCrawl-Bonus"]
ALLOW_SHARE_ALIKE = False        # True adds WikiMatrix: the model must then be published as CC BY-SA 4.0
EXTRA_TSV = ""                   # private only: /kaggle/input/<dataset>/distilled.tsv (en<TAB>vi)
BASE = "Helsinki-NLP/opus-mt-en-vi"
EPOCHS = 2
LR = 5e-5
BATCH = 64
EVAL_SAMPLES = 500               # dev sentences scored during training (generation is slow)
OUT = "/kaggle/working/screentrans-en-vi"
PUSH_TO = ""                     # e.g. "yourname/screentrans-en-vi" (needs the HF_TOKEN secret)
APP_MODELS_REPO = "anhbui02/screentrans-models"  # the apps' model list: exported + published here ("" = off)
'''),
    code('''
!pip -q install sacrebleu sentencepiece
'''),
    code('''
import sys, subprocess, pathlib
if not pathlib.Path("/kaggle/working/ScreenTrans").exists():
    subprocess.run(["git", "clone", "--depth", "1", REPO, "/kaggle/working/ScreenTrans"], check=True)
sys.path.insert(0, "/kaggle/working/ScreenTrans")
'''),
    code('''
# ---- build the dataset (open corpora only) ----
import ast, json, urllib.request
from pathlib import Path
from training.corpora import CORPORA, build, resolve_url

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

def download(corpus, dest):
    url = resolve_url(corpus, fetch_json)
    print("downloading", corpus.name, url)
    urllib.request.urlretrieve(url, dest)
    return dest

# the game sample sentences are the evaluation set: they never enter training
src = Path("/kaggle/working/ScreenTrans/windows/scripts/compare_engines.py").read_text(encoding="utf-8")
SAMPLES = next(ast.literal_eval(n.value) for n in ast.parse(src).body
               if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SAMPLES")
chosen = [c for c in CORPORA if c.name in CORPORA_ON or (ALLOW_SHARE_ALIKE and c.share_alike)]
stats = build(Path("/kaggle/working/data"), chosen, download=download, heldout=set(SAMPLES))
print(stats)
'''),
    code('''
# ---- tokenize ----
import datasets
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

tok = AutoTokenizer.from_pretrained(BASE)
def load_tsv(path):
    rows = [l.rstrip("\\n").split("\\t") for l in open(path, encoding="utf-8") if "\\t" in l]
    return {"en": [r[0] for r in rows], "vi": [r[1] for r in rows]}

train = load_tsv("/kaggle/working/data/train.tsv")
if EXTRA_TSV:
    extra = load_tsv(EXTRA_TSV)
    train = {k: train[k] + extra[k] for k in train}
ds = datasets.DatasetDict({
    "train": datasets.Dataset.from_dict(train),
    "dev": (dev := datasets.Dataset.from_dict(load_tsv("/kaggle/working/data/dev.tsv"))).select(
        range(min(EVAL_SAMPLES, len(dev)))),
})
def prep(b):
    x = tok(b["en"], max_length=128, truncation=True)
    x["labels"] = tok(text_target=b["vi"], max_length=128, truncation=True)["input_ids"]
    return x
tds = ds.map(prep, batched=True, remove_columns=["en", "vi"])
print(tds)
'''),
    code('''
# ---- train ----
import numpy as np, sacrebleu
from transformers import DataCollatorForSeq2Seq, Seq2SeqTrainer, Seq2SeqTrainingArguments

model = AutoModelForSeq2SeqLM.from_pretrained(BASE)
def compute_metrics(p):
    preds, labels = p
    preds = np.where(preds != -100, preds, tok.pad_token_id)
    labels = np.where(labels != -100, labels, tok.pad_token_id)
    hyp = tok.batch_decode(preds, skip_special_tokens=True)
    ref = tok.batch_decode(labels, skip_special_tokens=True)
    return {"chrf": sacrebleu.corpus_chrf(hyp, [ref]).score, "bleu": sacrebleu.corpus_bleu(hyp, [ref]).score}

# warmup as a step count: transformers 5 dropped warmup_ratio
import math, torch
steps = math.ceil(len(tds["train"]) / (BATCH * max(1, torch.cuda.device_count()))) * EPOCHS
args = Seq2SeqTrainingArguments(
    output_dir="/kaggle/working/ckpt", per_device_train_batch_size=BATCH, per_device_eval_batch_size=BATCH,
    learning_rate=LR, num_train_epochs=EPOCHS, warmup_steps=int(steps * 0.03), weight_decay=0.01, fp16=True,
    eval_strategy="steps", eval_steps=2000, save_steps=2000, save_total_limit=2, logging_steps=200,
    load_best_model_at_end=True, metric_for_best_model="chrf", greater_is_better=True,
    predict_with_generate=True, generation_max_length=128, report_to="none",
)
trainer = Seq2SeqTrainer(model=model, args=args, train_dataset=tds["train"], eval_dataset=tds["dev"],
                         data_collator=DataCollatorForSeq2Seq(tok, model=model), compute_metrics=compute_metrics)
base_scores = Seq2SeqTrainer(model=AutoModelForSeq2SeqLM.from_pretrained(BASE), args=args, eval_dataset=tds["dev"],
                             data_collator=DataCollatorForSeq2Seq(tok), compute_metrics=compute_metrics).evaluate()
print("base model:", base_scores)
trainer.train()
fine_scores = trainer.evaluate()
print("fine-tuned:", fine_scores)
'''),
    code('''
# ---- game sentences, side by side (judge by eye: they were never trained on) ----
import torch
base = AutoModelForSeq2SeqLM.from_pretrained(BASE).to(trainer.model.device).eval()
def translate(m, sents):
    x = tok(sents, return_tensors="pt", padding=True, truncation=True).to(m.device)
    with torch.no_grad():
        out = m.generate(**x, num_beams=4, max_length=128)
    return tok.batch_decode(out, skip_special_tokens=True)
for s, a, b in zip(SAMPLES, translate(base, SAMPLES), translate(trainer.model.eval(), SAMPLES)):
    print(f"EN  {s}\\nOLD {a}\\nNEW {b}\\n")
'''),
    code('''
# ---- save (+ licenses and a model card) ----
import shutil
trainer.save_model(OUT)
tok.save_pretrained(OUT)
shutil.copy("/kaggle/working/data/DATA_LICENSES.md", OUT)
private = bool(EXTRA_TSV)
license_line = "cc-by-sa-4.0" if ALLOW_SHARE_ALIKE else "apache-2.0"
Path(OUT, "README.md").write_text(f"""---
license: {license_line}
language: [en, vi]
base_model: {BASE}
---
# screentrans-en-vi

`{BASE}` (Helsinki-NLP / OPUS-MT, Tiedemann & Thottingal 2020) fine-tuned for game dialogue in ScreenTrans
on openly licensed data listed in DATA_LICENSES.md.
{"**PRIVATE: trained with LLM-generated data — do not publish.**" if private else ""}
""", encoding="utf-8")
shutil.make_archive("/kaggle/working/screentrans-en-vi", "zip", OUT)
print("saved", OUT)
'''),
    code('''
# ---- optional: publish to Hugging Face ----
if PUSH_TO and not EXTRA_TSV:
    from huggingface_hub import HfApi
    from kaggle_secrets import UserSecretsClient
    api = HfApi(token=UserSecretsClient().get_secret("HF_TOKEN"))
    api.create_repo(PUSH_TO, exist_ok=True)
    api.upload_folder(folder_path=OUT, repo_id=PUSH_TO)
    print("published https://huggingface.co/" + PUSH_TO)
elif PUSH_TO:
    print("not published: this model used private (LLM-generated) data")
'''),
    code('''
# ---- publish to the apps: export CTranslate2 (Windows) + ONNX (Android), upload with a new version ----
import datetime, os, subprocess, sys
REPO_DIR = "/kaggle/working/ScreenTrans"
MANIFEST = f"https://huggingface.co/{APP_MODELS_REPO}/resolve/main/manifest.json"
better = fine_scores.get("eval_chrf", 0) > base_scores.get("eval_chrf", 0)
token = ""
if APP_MODELS_REPO and not EXTRA_TSV and better:
    try:
        from kaggle_secrets import UserSecretsClient
        token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception as e:
        print("no HF_TOKEN secret (Add-ons → Secrets, a write token):", e)

def sh(*args, check=True):
    print("$", " ".join(args))
    return subprocess.run(list(args), cwd=REPO_DIR, check=check).returncode

if not APP_MODELS_REPO:
    print("APP_MODELS_REPO is empty: not published to the apps")
elif EXTRA_TSV:
    print("not published to the apps: this model used private (LLM-generated) data")
elif ALLOW_SHARE_ALIKE:
    print("not published to the apps: share-alike data (CC BY-SA) — the app's model list says apache-2.0")
elif not better:
    print(f"not published: chrF {fine_scores.get('eval_chrf', 0):.2f} is not above the base model's "
          f"{base_scores.get('eval_chrf', 0):.2f}")
elif token:
    sh(sys.executable, "-m", "pip", "-q", "install", "ctranslate2", "sentencepiece", "sacremoses")
    sh(sys.executable, "-m", "models.export", "ct2", "screentrans-en-vi", "--hf-id", OUT)
    # ONNX needs optimum: if this Kaggle image's libraries do not fit, Windows still gets the model
    onnx_ok = (sh(sys.executable, "-m", "pip", "-q", "install", "optimum[onnxruntime]", "onnx", check=False) == 0
               and sh(sys.executable, "-m", "models.export", "onnx", "screentrans-en-vi", "--hf-id", OUT, check=False) == 0)
    if not onnx_ok:
        print("ONNX export failed: only the Windows model is published this time")
    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")
    subprocess.run([sys.executable, "-m", "models.manifest", "--version", version, "--stage", "/kaggle/working/hf",
                    "--only", "screentrans-en-vi", "--merge-from", MANIFEST, "--upload", APP_MODELS_REPO, "--yes"],
                   cwd=REPO_DIR, check=True, env={**os.environ, "HF_TOKEN": token})
    print(f"published version {version}: the apps list it in Settings → Model (Có bản mới)")
'''),
]


def main() -> None:
    nb = {"cells": CELLS, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
