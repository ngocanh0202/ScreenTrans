# Phase 0 — Khởi tạo monorepo, CI khung & 3 spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng khung monorepo + CI chạy được, và trả lời bằng số liệu 3 câu hỏi rủi ro: OCR nào đọc tốt chữ game (A), CTranslate2 có cho output khớp `transformers` với opus-mt/vinai không và nhanh bao nhiêu (B), opus-mt ONNX có chạy đủ nhanh trên POCO X8 Pro không (C).

**Architecture:** Monorepo `windows/` (Python), `models/` (script export/verify), `spikes/` (mã thử nghiệm, giữ lại để tham khảo), `android/` (Gradle, Kotlin). Spike C tách logic thuần Kotlin (tokenizer + vòng giải mã) thành module JVM test được trên CI bằng ONNX Runtime bản desktop, app Android chỉ là vỏ đo hiệu năng. Máy dev không có Android SDK → APK build trên GitHub Actions, người dùng tải artifact về cài lên điện thoại.

**Tech Stack:** Python 3.11 (qua `uv`), pytest, winocr, rapidocr_onnxruntime, transformers, ctranslate2, optimum[onnxruntime], sentencepiece; Kotlin, Gradle (wrapper), JDK 17, ONNX Runtime (Android + desktop JVM), GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md) và [AGENT.md](../../../AGENT.md) (mục 15, Phase 0).

## Global Constraints

- Python **3.11** cho mọi mã Python (máy dev đang có 3.14 → dùng `uv python install 3.11`, venv tại `.venv` ở gốc repo).
- **Không dùng GPU** cho OCR/dịch: `ctranslate2` `device="cpu"`, `compute_type="int8"`, `intra_threads=2`, `inter_threads=1`; ORT chỉ CPU EP (XNNPACK thử thêm ở spike C).
- `beam_size` mặc định 2 (Windows); Android giải mã greedy.
- vinai: tokenizer `src_lang="en_XX"`, CT2 `target_prefix=[["vi_VN"]]`.
- Android: minSdk **29**, targetSdk mới nhất mà AGP ổn định hỗ trợ; JDK **17** trên CI.
- Không gọi API dịch online. Model và output export **không commit** (`.gitignore`).
- Làm trên nhánh `phase-0`, commit thường xuyên; mỗi commit kết thúc bằng dòng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Gói ngôn ngữ English OCR chưa cài** (Windows tiếng Việt) → `winocr` phải báo lỗi rõ ràng kèm hướng dẫn cài, không crash với traceback khó hiểu. Test ở Task 3.
2. **Câu có token lạ / rỗng / rất dài** (tên riêng, ký tự đặc biệt `★`, chuỗi rỗng, câu > 200 token) → export/verify và decoder Kotlin không treo, có `max_length`. Test ở Task 4 và Task 6.
3. **Chuẩn hóa SentencePiece** (NFKC, nhiều khoảng trắng, dấu nháy cong `“ ”`, `…`) — tokenizer Kotlin phải cho đúng id như Python. Test golden ở Task 6.
4. **vinai sinh lặp token ngôn ngữ / thiếu `vi_VN`** → so sánh CT2 vs transformers phải phát hiện được (bỏ prefix trước khi so). Test ở Task 4.
5. **Ảnh OCR có nền trong suốt/alpha hoặc rất nhỏ (< 20 px chiều cao)** → harness OCR chuyển RGB và phóng to, không lỗi. Test ở Task 3.

---

### Task 1: Khung monorepo + môi trường Python

**Files:**
- Create: `.gitignore`, `README.md`, `.python-version` (`3.11`)
- Create: `windows/requirements.txt`, `windows/requirements-dev.txt`, `windows/app/__init__.py`, `windows/tests/test_smoke.py`, `pytest.ini` (gốc repo)
- Create: `shared/README.md`, `models/requirements.txt`, `spikes/requirements.txt`

**Interfaces:**
- Produces: venv `.venv` (Python 3.11); **một** `pytest.ini` ở gốc repo: `pythonpath = . windows`, `testpaths = windows/tests spikes/tests models/tests`, `markers = local: cần máy dev (winocr, model đã export)`. Lệnh test chuẩn (chạy ở gốc repo): `.venv\Scripts\python -m pytest -q`; CI: `... -m "not local"`. `app` (từ `windows/`), `spikes`, `models` đều import được.
- Quy ước: module trong `models/` và `spikes/` **import thư viện nặng (torch, transformers, ctranslate2, onnxruntime, winocr, rapidocr) bên trong hàm**, để test thuần chạy trên CI chỉ với `pytest` + `pillow`.

- [ ] **Step 1:** Tạo nhánh: `git checkout -b phase-0`.
- [ ] **Step 2:** Viết `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `models/out/`, `spikes/out/`, `android/.gradle/`, `android/**/build/`, `android/local.properties`, `android/app/src/main/assets/model/`, `*.keystore`, `data/`.
- [ ] **Step 3:** Viết test smoke `windows/tests/test_smoke.py`:

```python
import sys
import app

def test_python_version():
    assert sys.version_info[:2] == (3, 11)

def test_app_package_importable():
    assert app.__name__ == "app"
```

- [ ] **Step 4:** Tạo venv và chạy test (phải FAIL vì chưa có `windows/app/__init__.py`):
  `uv python install 3.11; uv venv --python 3.11 .venv; uv pip install --python .venv -r windows/requirements-dev.txt; .venv\Scripts\python -m pytest windows/tests -q`
  Expected: FAIL `ModuleNotFoundError: No module named 'app'`.
- [ ] **Step 5:** Tạo `windows/app/__init__.py` (rỗng), `pytest.ini` ở gốc như Interfaces. `windows/requirements.txt` để trống có chú thích (Phase 1 điền); `windows/requirements-dev.txt` = `-r requirements.txt` + `pytest`. `models/requirements.txt`: `transformers`, `sentencepiece`, `ctranslate2`, `optimum[onnxruntime]`, `torch` (CPU, `--index-url https://download.pytorch.org/whl/cpu` ghi trong README), `sacrebleu`. `spikes/requirements.txt`: `winocr`, `rapidocr_onnxruntime`, `pillow`.
- [ ] **Step 6:** Chạy lại `.venv\Scripts\python -m pytest -q` (gốc repo) → Expected: `2 passed`.
- [ ] **Step 7:** `README.md`: mô tả 1 đoạn, cấu trúc thư mục, lệnh tạo venv/chạy test, link spec + AGENT.md.
- [ ] **Step 8:** Commit `chore: scaffold monorepo and python env`.

### Task 2: CI khung (Python)

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: lệnh test của Task 1.
- Produces: workflow `ci` với job `python-tests` (`windows-latest`); Task 7 thêm job `android` vào cùng file.

- [ ] **Step 1:** Viết `ci.yml`: trigger `push` + `pull_request`; job `python-tests` trên `windows-latest`: `actions/checkout@v4`, `astral-sh/setup-uv@v6`, `uv python install 3.11`, `uv venv --python 3.11 .venv`, `uv pip install --python .venv -r windows/requirements-dev.txt -r spikes/requirements-ci.txt`, chạy `.venv\Scripts\python -m pytest -q -m "not local"` ở gốc repo.
  Tạo `spikes/requirements-ci.txt` chỉ gồm thư viện nhẹ mà test thuần cần (`pillow`).
- [ ] **Step 2:** Commit `ci: add python test workflow`.
- [ ] **Step 3:** Push nhánh: `git push -u origin phase-0`. Kiểm tra trên GitHub tab Actions (hoặc nhờ người dùng xem) → Expected: job `python-tests` xanh.

### Task 3: Spike A — OCR trên ảnh chụp game

**Files:**
- Create: `spikes/ocr/metrics.py`, `spikes/ocr/engines.py`, `spikes/ocr/run.py`, `spikes/tests/test_ocr_metrics.py`, `spikes/tests/test_ocr_engines.py`, `spikes/ocr/data/README.md`
- Data (người dùng cung cấp): `spikes/ocr/data/*.png` + `*.txt` cùng tên (text đúng)

**Interfaces:**
- Produces:
  - `cer(ref: str, hyp: str) -> float` — Levenshtein ký tự / `len(ref)` sau chuẩn hóa khoảng trắng (gộp mọi whitespace thành 1 space, strip); `ref` rỗng → `0.0` nếu `hyp` rỗng, ngược lại `1.0`.
  - `prepare_image(img: PIL.Image.Image, min_height: int = 32) -> PIL.Image.Image` — chuyển RGB (bỏ alpha, nền trắng), phóng to giữ tỉ lệ nếu cao < `min_height`.
  - `class OcrEngineUnavailable(Exception)`; `windows_ocr(img) -> str`, `rapid_ocr(img) -> str` — trả text các dòng nối bằng `\n`. `windows_ocr` ném `OcrEngineUnavailable` với thông điệp chứa `"Settings > Time & language > Language"` khi thiếu gói English.
  - `python -m spikes.ocr.run` → in bảng: ảnh, engine, CER, ms (trung vị 5 lần, bỏ lần đầu) và ghi `spikes/out/ocr_results.json`.

- [ ] **Step 1:** Viết test `spikes/tests/test_ocr_metrics.py`:

```python
from PIL import Image
from spikes.ocr.metrics import cer, prepare_image

def test_cer_identical():
    assert cer("We have to leave.", "We  have to leave.") == 0.0

def test_cer_one_substitution():
    assert cer("abcd", "abxd") == 0.25

def test_cer_empty_ref():
    assert cer("", "") == 0.0
    assert cer("", "x") == 1.0

def test_prepare_image_drops_alpha_and_upscales():
    img = Image.new("RGBA", (100, 16), (0, 0, 0, 0))
    out = prepare_image(img, min_height=32)
    assert out.mode == "RGB"
    assert out.size == (200, 32)
```

- [ ] **Step 2:** Chạy `.venv\Scripts\python -m pytest spikes/tests/test_ocr_metrics.py -q` → FAIL (module chưa có).
- [ ] **Step 3:** Cài `uv pip install --python .venv -r spikes/requirements.txt`; tạo `spikes/__init__.py`, `spikes/ocr/__init__.py`, `spikes/tests/__init__.py`; implement `cer`, `prepare_image` trong `metrics.py` (Levenshtein tự viết, DP 2 hàng).
- [ ] **Step 4:** Chạy lại → Expected: `4 passed`.
- [ ] **Step 5:** Viết `spikes/tests/test_ocr_engines.py` (đánh dấu `@pytest.mark.local`): tạo ảnh 600×80 nền đen chữ trắng "Hello world" bằng `ImageFont.truetype("segoeui.ttf", 40)`; assert `"hello world" in windows_ocr(img).lower()` và tương tự `rapid_ocr`. Thêm test monkeypatch `winocr` để mô phỏng thiếu ngôn ngữ (hàm gốc ném lỗi) → assert `OcrEngineUnavailable` và thông điệp chứa `"Language"` (test này **không** đánh dấu `local` — monkeypatch nên chạy được trên CI).
- [ ] **Step 6:** Implement `engines.py`: `windows_ocr` dùng `winocr.recognize_pil_sync(img, "en")` (gọi `prepare_image` trước), bắt lỗi khi ngôn ngữ không khả dụng → `OcrEngineUnavailable`; `rapid_ocr` dùng `rapidocr_onnxruntime.RapidOCR()` khởi tạo 1 lần (module-level lazy), sắp dòng theo y rồi x. Chạy `pytest spikes/tests -q` → Expected: tất cả pass (trên máy dev).
- [ ] **Step 7:** Implement `run.py`: duyệt `spikes/ocr/data/*.png`, đọc `.txt` cùng tên, chạy 2 engine, in bảng + ghi JSON. `data/README.md` hướng dẫn người dùng: chụp 8–10 ảnh **chỉ vùng khung thoại** Reverse: 1999 (có tên nhân vật, có câu lựa chọn, có nền mờ), lưu `.png`, gõ text đúng vào `.txt`.
- [ ] **Step 8:** **Dừng, nhờ người dùng cung cấp ảnh.** Sau khi có ảnh: chạy `.venv\Scripts\python -m spikes.ocr.run`. Expected: bảng kết quả; ghi số liệu vào báo cáo Task 8.
- [ ] **Step 9:** Commit `spike(ocr): windows ocr vs rapidocr harness` (ảnh mẫu được commit nếu người dùng đồng ý; mặc định không — thêm `spikes/ocr/data/*.png` vào `.gitignore`).

### Task 4: Spike B — Export CT2 + so sánh với transformers

**Files:**
- Create: `models/__init__.py`, `models/registry.py`, `models/export.py`, `models/verify.py`, `models/sentences_en.txt`, `models/tests/__init__.py`, `models/tests/test_verify.py`

**Interfaces:**
- Produces:
  - `models/registry.py`: `MODELS: dict[str, ModelSpec]` với `ModelSpec(hf_id: str, kind: Literal["marian","mbart"], src_lang: str | None, tgt_prefix: str | None)`; khóa `"opus-mt-en-vi"` → `Helsinki-NLP/opus-mt-en-vi`, marian, None, None; `"vinai-en2vi"` → `vinai/vinai-translate-en2vi-v2`, mbart, `"en_XX"`, `"vi_VN"`.
  - `python -m models.export ct2 <key>` → `models/out/<key>-ct2/` (int8, copy tokenizer files vào cùng thư mục).
  - `strip_prefix(tokens: list[str], prefix: str | None) -> list[str]` — bỏ **mọi** lần xuất hiện `prefix` ở đầu danh sách.
  - `agreement(ref: list[str], hyp: list[str]) -> float` — tỉ lệ câu khớp chính xác sau `" ".join(s.split())`.
  - `python -m models.verify ct2 <key> [--beam 1|2]` → in: tỉ lệ khớp (beam 1, so với `transformers` `generate(num_beams=1, max_new_tokens=256)`), latency trung vị/p95 mỗi câu và cho batch toàn bộ (`intra_threads=2`, beam 2), RAM RSS sau load (psutil), kích thước thư mục; ghi `models/out/verify_<key>_ct2.json`.

- [ ] **Step 1:** Viết `models/tests/test_verify.py`:

```python
from models.verify import strip_prefix, agreement
from models.registry import MODELS

def test_strip_prefix_removes_repeated_lang_token():
    assert strip_prefix(["vi_VN", "vi_VN", "▁Xin", "▁chào"], "vi_VN") == ["▁Xin", "▁chào"]

def test_strip_prefix_none():
    assert strip_prefix(["▁a"], None) == ["▁a"]

def test_agreement_normalizes_whitespace():
    assert agreement(["Xin  chào", "b"], ["Xin chào", "c"]) == 0.5

def test_registry_vinai_lang_tokens():
    spec = MODELS["vinai-en2vi"]
    assert (spec.src_lang, spec.tgt_prefix) == ("en_XX", "vi_VN")
```

- [ ] **Step 2:** Chạy `.venv\Scripts\python -m pytest models/tests -q` → FAIL. (Test này thuần, chạy trên CI — `verify.py` không import thư viện nặng ở đầu file.)
- [ ] **Step 3:** Cài `uv pip install --python .venv -r models/requirements.txt` (torch CPU index); implement `registry.py`, `strip_prefix`, `agreement`. Chạy lại → Expected: `4 passed`.
- [ ] **Step 4:** Viết `models/sentences_en.txt`: 30 câu kiểu thoại game (ngắn/dài, tên riêng "Vertin", "Sonetto", ký tự `★`, dấu nháy cong, `…`, 1 câu ~60 từ, 1 dòng rỗng để kiểm tra bỏ qua).
- [ ] **Step 5:** Implement `export.py ct2` dùng `ctranslate2.converters.TransformersConverter(hf_id, copy_files=[...tokenizer files...]).convert(out_dir, quantization="int8", force=True)`. Chạy cho cả 2 key → Expected: thư mục có `model.bin`, ghi kích thước.
- [ ] **Step 6:** Implement `verify.py ct2`: tokenizer `AutoTokenizer` (vinai: `src_lang="en_XX"`); CT2 `Translator(dir, device="cpu", compute_type="int8", intra_threads=2, inter_threads=1)`; `translate_batch(tokens, beam_size=..., max_decoding_length=256, target_prefix=[[prefix]]*n nếu có)`; output → `strip_prefix` → `convert_tokens_to_string`. Bản tham chiếu transformers (vinai: `forced_bos_token_id=tokenizer.lang_code_to_id["vi_VN"]`). Bỏ qua dòng rỗng. **Lưu ý:** tham chiếu chạy fp32, CT2 int8 → khớp tuyệt đối không bắt buộc; ghi thêm chrF giữa hai bản (`sacrebleu.sentence_chrf`).
- [ ] **Step 7:** Chạy `python -m models.verify ct2 opus-mt-en-vi` và `... vinai-en2vi`. **Tiêu chí đạt:** chrF trung bình CT2 vs transformers ≥ 90, không câu nào chứa `vi_VN`/`en_XX` trong output, không câu rỗng với input khác rỗng. Ghi số liệu cho Task 8.
- [ ] **Step 8:** Commit `spike(models): ct2 export and verify vs transformers`.

### Task 5: Spike C (phần Python) — Export ONNX + bản giải mã tham chiếu + golden

**Files:**
- Create: `models/onnx_ref.py`, `models/sp_export.py`, `models/tests/test_onnx_ref.py`
- Modify: `models/export.py` (thêm lệnh `onnx`)

**Interfaces:**
- Consumes: `MODELS`, `sentences_en.txt` (Task 4).
- Produces:
  - `python -m models.export onnx opus-mt-en-vi` → `models/out/opus-mt-en-vi-onnx/` gồm `encoder_model.onnx`, `decoder_model_merged.onnx` (int8 dynamic quantization), `source.spm`, `vocab.json`, `config.json`; thêm `sp_source.json` từ `sp_export.py`.
  - `sp_export.py`: `export_sp(spm_path: Path, out: Path) -> None` ghi JSON `{"pieces": [[piece, score, type], ...], "unk_id": int, "normalizer": "nmt_nfkc"}` đọc bằng `sentencepiece` `ModelProto`.
  - `onnx_ref.py`: `greedy_translate(texts: list[str], model_dir: Path, max_len: int = 256) -> list[list[int]]` — giải mã greedy bằng `onnxruntime` (encoder 1 lần; decoder merged với `use_cache_branch`, KV-cache), dừng ở `eos_token_id`; `decoder_start_token_id` = `pad_token_id` của Marian.
  - `python -m models.onnx_ref golden` → `models/out/golden_opus.json`: list `{"text", "src_ids", "out_ids", "out_text"}` cho mọi câu trong `sentences_en.txt` (`src_ids` từ `MarianTokenizer`, kèm `</s>`).

- [ ] **Step 1:** Viết `models/tests/test_onnx_ref.py` (`@pytest.mark.local`, cần model đã export): (a) `greedy_translate(["Hello."], dir)` trả list 1 phần tử, kết thúc bằng `eos_token_id`; (b) với 10 câu đầu, decode `out_ids` bằng `MarianTokenizer` và so với `transformers` `generate(num_beams=1)` fp32 → chrF trung bình ≥ 90; (c) câu 300 từ → độ dài output ≤ `max_len`.
- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Implement `export.py onnx` bằng `optimum.exporters.onnx.main_export(hf_id, output, task="text2text-generation-with-past")` rồi `onnxruntime.quantization.quantize_dynamic(..., weight_type=QuantType.QInt8)` cho từng file; copy `source.spm`, `vocab.json`; gọi `export_sp`.
- [ ] **Step 4:** Implement `greedy_translate` (đọc tên input/output từ session, không hardcode số layer). Chạy test → Expected: pass.
- [ ] **Step 5:** Chạy `python -m models.onnx_ref golden` → file golden tồn tại, 29 mục (bỏ dòng rỗng). Ghi kích thước thư mục ONNX.
- [ ] **Step 6:** Commit `spike(models): onnx export, python greedy reference, golden outputs`.

### Task 6: Spike C (phần Kotlin) — tokenizer + giải mã thuần JVM

**Files:**
- Create: `android/settings.gradle.kts`, `android/build.gradle.kts`, `android/gradle.properties`, Gradle wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/*`)
- Create: `android/mt-core/build.gradle.kts` (Kotlin JVM lib), `android/mt-core/src/main/kotlin/screentrans/mt/SentencePieceUnigram.kt`, `.../MarianVocab.kt`, `.../GreedyDecoder.kt`, `.../OrtSessions.kt`
- Test: `android/mt-core/src/test/kotlin/screentrans/mt/GoldenTest.kt`

**Interfaces:**
- Consumes: `sp_source.json`, `vocab.json`, 2 file ONNX, `golden_opus.json` (Task 5). Test đọc thư mục qua system property `mt.modelDir` (mặc định `../../models/out/opus-mt-en-vi-onnx`) và `mt.golden`; thiếu file → test **skip** (`Assumptions.assumeTrue`), không fail.
- Produces:
  - `class SentencePieceUnigram(json: String) { fun encode(text: String): List<String> }` — chuẩn hóa NFKC + gộp whitespace + thêm `▁` đầu từ, Viterbi trên điểm piece; ký tự không có piece → `<unk>`.
  - `class MarianVocab(json: String) { fun ids(pieces: List<String>): IntArray /* + eos */; fun decode(ids: IntArray): String /* bỏ special, nối, ▁→space, trim */ }`
  - `interface Seq2SeqModel { fun encode(ids: IntArray): EncoderOut; fun step(state: DecoderState, lastToken: Int): Pair<FloatArray, DecoderState> }` và `class OrtSeq2Seq(modelDir: File, threads: Int = 2) : Seq2SeqModel, AutoCloseable` (ORT Java API `ai.onnxruntime`).
  - `fun greedyDecode(model: Seq2SeqModel, srcIds: IntArray, startId: Int, eosId: Int, maxLen: Int = 256): IntArray`
  - `class Translator(modelDir: File, threads: Int = 2) { fun translate(text: String): String }` gom các phần trên.
- Dependency: `mt-core` dùng `com.microsoft.onnxruntime:onnxruntime` (desktop) cho test JVM; Task 7 app dùng `onnxruntime-android` với **cùng** API Java `ai.onnxruntime` → `mt-core` khai báo ORT là `compileOnly`, test thêm `testImplementation` bản desktop, app thêm `implementation` bản android.

- [ ] **Step 1:** Viết `GoldenTest.kt`:
  - `tokenizer matches python ids`: với mọi mục golden, `vocab.ids(sp.encode(text))` == `src_ids`. Báo số câu lệch và in câu đầu tiên lệch.
  - `greedy decode matches python`: với mọi mục, `greedyDecode(...)` == `out_ids`.
  - `decode text`: `vocab.decode(out_ids)` == `out_text` (sau gộp whitespace).
  - `fake model stops at maxLen`: `Seq2SeqModel` giả luôn trả logits max ở token 5 → kết quả dài đúng `maxLen`.
  - `empty input`: `translate("")` == `""` không gọi model.
- [ ] **Step 2:** Tạo khung Gradle (wrapper bản ổn định mới nhất tương thích AGP; JVM toolchain 17). Chạy `cd android; ./gradlew :mt-core:test` trên CI (máy dev có JDK 25 — nếu wrapper không chạy được với 25 thì chỉ chạy trên CI hoặc cài JDK 17 qua `winget install EclipseAdoptium.Temurin.17.JDK`). Expected: FAIL (chưa có class).
- [ ] **Step 3:** Implement `SentencePieceUnigram`, `MarianVocab`, `GreedyDecoder`, `OrtSeq2Seq`, `Translator`.
- [ ] **Step 4:** Chạy `./gradlew :mt-core:test -Dmt.modelDir=... -Dmt.golden=...` (máy có model) → Expected: tất cả pass. **Tiêu chí đạt:** tokenizer khớp ≥ 28/29 câu, greedy khớp hoàn toàn với các câu tokenizer khớp. Nếu tokenizer lệch nhiều → ghi lại nguyên nhân (thường do chuẩn hóa) cho báo cáo; không cố hoàn hảo trong spike.
- [ ] **Step 5:** Commit `spike(android): pure-jvm sentencepiece + greedy decoder with golden tests`.

### Task 7: Spike C (app Android) — đo trên POCO X8 Pro qua APK từ CI

**Files:**
- Create: `android/app/build.gradle.kts` (application, minSdk 29, `noCompress += "onnx"`), `android/app/src/main/AndroidManifest.xml`, `android/app/src/main/kotlin/screentrans/spike/BenchActivity.kt`, `android/app/src/main/res/layout/activity_bench.xml`
- Create: `.github/workflows/android-spike.yml`
- Modify: `.github/workflows/ci.yml` (thêm job `android-unit`: JDK 17, `./gradlew :mt-core:test` — golden thiếu → test skip)

**Interfaces:**
- Consumes: `Translator` (Task 6), `models.export onnx`, `models.onnx_ref golden` (Task 5).
- Produces: artifact `screentrans-spike-debug.apk` trên GitHub Actions; màn hình đo hiển thị kết quả để người dùng chụp lại.

- [ ] **Step 1:** `BenchActivity`: khi bấm nút "Chạy" (chạy trên background thread): copy model từ `assets/model/` sang `filesDir` (lần đầu), đo thời gian load `Translator`; dịch 1 câu khởi động (bỏ qua); với 20 câu đầu trong `assets/model/sentences.txt` đo ms mỗi câu ×3 lần; đo RAM (`Debug.getPss()` hoặc `ActivityManager.getProcessMemoryInfo`) sau khi chạy; chạy lại với 4 luồng và với XNNPACK EP (`SessionOptions.addXnnpack(mapOf("intra_op_num_threads" to "2"))`) nếu thêm được. Hiển thị: load ms, trung vị/p95 ms/câu cho mỗi cấu hình, RAM MB, 3 bản dịch mẫu, và cờ "khớp golden" cho 20 câu.
- [ ] **Step 2:** `android-spike.yml` (`workflow_dispatch` + push vào `phase-0` khi đổi `android/**` hoặc `models/**`), `ubuntu-latest`: setup Python 3.11 + uv, cài `models/requirements.txt`, chạy `models.export onnx opus-mt-en-vi` và `models.onnx_ref golden`, copy thư mục ONNX + `sentences_en.txt` (→ `sentences.txt`) + golden vào `android/app/src/main/assets/model/`; setup JDK 17; `./gradlew :mt-core:test -Dmt.modelDir=... -Dmt.golden=...` (lúc này golden có thật → test chạy thật); `./gradlew :app:assembleDebug`; upload artifact APK. Cache pip/HF/Gradle.
- [ ] **Step 3:** Push, chờ workflow. Expected: job xanh, golden test **chạy** (không skip) và pass, có artifact APK (~100–150 MB).
- [ ] **Step 4:** **Dừng, nhờ người dùng:** tải APK từ trang Actions, cài lên POCO X8 Pro (cho phép cài từ nguồn không xác định), mở app, bấm "Chạy", chụp màn hình kết quả gửi lại.
- [ ] **Step 5:** Commit `spike(android): benchmark app and CI apk build`.

### Task 8: Báo cáo Phase 0 & chốt quyết định

**Files:**
- Create: `docs/superpowers/reports/2026-xx-xx-phase0-results.md`
- Modify: `AGENT.md` (đánh dấu Phase 0 xong; điền model/OCR mặc định đã chốt), spec mục 5.1/5.2 nếu quyết định khác dự kiến

- [ ] **Step 1:** Viết báo cáo: bảng OCR (CER, ms theo engine, ảnh nào sai và vì sao), bảng dịch Windows (opus vs vinai: chrF khớp, ms/câu, ms/batch 50 từ, RAM, dung lượng, 5 bản dịch mẫu cạnh nhau), bảng Android (load, ms/câu theo cấu hình, RAM, khớp golden, dung lượng APK).
- [ ] **Step 2:** Chốt theo tiêu chí spec: OCR mặc định (Windows OCR nếu CER ≤ RapidOCR + 2 điểm và nhanh hơn); model Windows (vinai nếu batch ~50 từ beam 2 < 300 ms để còn chỗ cho OCR trong ngân sách 500 ms, không thì opus); Android (ONNX opus nếu < ~300 ms/câu ~20 từ và RAM < 400 MB, không thì ML Kit Translation); cấu hình luồng/XNNPACK tốt nhất.
- [ ] **Step 3:** Cập nhật `AGENT.md` mục 15 (tick Phase 0) và các mục bị ảnh hưởng.
- [ ] **Step 4:** Chạy toàn bộ test local (`pytest windows/tests spikes/tests models/tests -q`) và xác nhận CI xanh → Expected: pass.
- [ ] **Step 5:** Commit `docs: phase 0 results and decisions`; mở PR `phase-0` → `main` (nếu người dùng muốn; cần `gh` — máy chưa cài, hoặc người dùng tự mở trên web).
