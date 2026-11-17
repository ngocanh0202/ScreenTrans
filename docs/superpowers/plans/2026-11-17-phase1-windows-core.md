# Phase 1 — Lõi Windows (CLI) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m app.cli --image anh.png` (hoặc `--screen x,y,w,h`) đọc chữ tiếng Anh trong ảnh/vùng màn hình bằng Windows OCR, tách tên/đoạn/câu, bảo vệ thuật ngữ, dịch sang tiếng Việt bằng vinai (CTranslate2) có cache, và in kết quả — lõi mà GUI Phase 2–3 sẽ gọi lại.

**Architecture:** Package `windows/app/` gồm các module nhỏ ghép bằng `Pipeline`: `capture` → `ocr/windows_ocr` (trả `Line` có toạ độ) → `text/postprocess` (đoạn/tên/câu) → `cache` → `glossary` (placeholder) → `translate/ct2` → khôi phục thuật ngữ → `PipelineResult`. Model tải theo `manifest.json` (HF Hub) hoặc chỉ định thư mục local. Logic hậu xử lý được đặc tả bằng fixtures JSON dùng chung trong `shared/fixtures/postprocess/` (Kotlin dùng lại ở Phase 4).

**Tech Stack:** Python 3.11, pytest, PyYAML, Pillow, numpy, mss, winocr, ctranslate2, transformers + sentencepiece + sacremoses (tokenizer), jsonschema (dev), wordfreq (dev, sinh danh sách từ thông dụng).

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md), [AGENT.md](../../../AGENT.md) (mục 7–9, 12, 15 Phase 1), kết quả Phase 0: [docs/superpowers/reports/2026-11-17-phase0-results.md](../reports/2026-11-17-phase0-results.md).

## Global Constraints

- Python **3.11**, venv `.venv` ở gốc repo; test: `.venv\Scripts\python -m pytest -q` (CI: `-m "not local"`); test cần winocr/model/màn hình đánh dấu `@pytest.mark.local`.
- **Không dùng GPU**: CT2 `device="cpu"`, `compute_type="int8"`, `intra_threads=2`, `inter_threads=1`; `beam_size` mặc định 2.
- Model mặc định Windows: **`vinai-en2vi`** (tokenizer `src_lang="en_XX"`, `target_prefix=[["vi_VN"]]`); `opus-mt-en-vi` là tùy chọn.
- OCR mặc định: **Windows OCR** (RapidOCR **hoãn** — ~5 s/ảnh ở Phase 0).
- Không gọi API dịch online. Model không commit.
- Hiển thị/ghi tiếng Việt có dấu đúng trên console Windows (máy dev dùng code page **cp932**).
- Nguồn tối đa **512 token** (cắt bớt), đầu ra tối đa **256 token**.
- Thứ tự tra cứu: cache → thuật ngữ + model (`overrides`/sửa bản dịch thuộc Phase 3).
- Ngoài phạm vi Phase 1 (đã có Phase khác): hồ sơ game và vùng `name`/`choices` (Phase 3), RapidOCR (hoãn), GUI/overlay/phím tắt (Phase 2), Live (Phase 3).
- Nhánh `phase-1` từ `main`; mỗi commit kết thúc `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Ảnh không có chữ / chỉ có rác** → CLI in `(không tìm thấy chữ)` và thoát mã 0, không traceback. Test ở Task 9.
2. **Model làm hỏng placeholder thuật ngữ** → câu đó được dịch lại không dùng placeholder, kết quả vẫn có bản dịch. Test (translator giả xóa placeholder) ở Task 7.
3. **Thiếu model / tải dở / sai SHA-256** → thông báo rõ cách khắc phục, không để lại file hỏng được coi là hợp lệ. Test ở Task 10.
4. **Console Windows không phải UTF-8 (cp932)** → CLI vẫn in được tiếng Việt. Test subprocess ở Task 9.
5. **Đoạn OCR rất dài (> 512 token)** → không crash, vẫn có bản dịch. Test ở Task 6.

---

### Task 1: Cấu hình + phụ thuộc

**Files:**
- Modify: `windows/requirements.txt`, `windows/requirements-dev.txt`, `.github/workflows/ci.yml` (cài `windows/requirements-dev.txt` thay vì chỉ pytest)
- Create: `windows/config.yaml`, `windows/app/config.py`
- Test: `windows/tests/test_config.py`

**Interfaces:**
- Produces: `class ConfigError(Exception)`; `@dataclass Config` với các nhóm con `hotkeys`, `ocr`, `translator`, `overlay`, `live`, `cache`, `logging`, `models`, `paths` — giá trị mặc định **đúng như `config.yaml` mẫu trong AGENT.md mục 12**, thêm `paths.data_dir` (mặc định `%LOCALAPPDATA%\ScreenTrans`) và `translator.model_dir` (mặc định `None` = lấy theo manifest). `load_config(path: Path | None) -> Config`: `None`/file không tồn tại → mặc định; YAML ghi đè từng khóa; **khóa lạ → `ConfigError` nêu tên khóa** (bắt lỗi gõ sai).

- [ ] **Step 1:** Tạo nhánh `git checkout -b phase-1`. Cập nhật `windows/requirements.txt`: `pyyaml`, `pillow`, `numpy`, `mss`, `winocr`, `ctranslate2`, `transformers`, `sentencepiece`, `sacremoses`. `requirements-dev.txt`: `-r requirements.txt`, `pytest`, `jsonschema`, `wordfreq`. Cài: `uv pip install --python .venv -r windows/requirements-dev.txt`.
- [ ] **Step 2:** Viết test:

```python
def test_defaults_match_spec():
    c = load_config(None)
    assert c.translator.model == "vinai-en2vi" and c.translator.beam_size == 2 and c.translator.intra_threads == 2
    assert c.ocr.engine == "windows"
    assert (c.live.interval_ms, c.live.settle_ms, c.live.area_min_interval_ms) == (300, 250, 1000)
    assert c.hotkeys.translate_fullscreen == "ctrl+alt+f"

def test_yaml_overrides_one_key(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text("translator:\n  beam_size: 1\n", encoding="utf-8")
    c = load_config(p)
    assert c.translator.beam_size == 1 and c.translator.model == "vinai-en2vi"

def test_unknown_key_is_rejected(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text("translator:\n  beam_sise: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="beam_sise"):
        load_config(p)

def test_repo_config_yaml_loads():
    assert load_config(Path(__file__).parents[1] / "config.yaml").translator.model == "vinai-en2vi"
```

- [ ] **Step 3:** Chạy `pytest windows/tests/test_config.py -q` → FAIL (chưa có module).
- [ ] **Step 4:** Implement `config.py` (dataclass lồng nhau, merge dict đệ quy, `ConfigError`); viết `windows/config.yaml` = mẫu AGENT.md + `paths`. Chạy lại → PASS.
- [ ] **Step 5:** Sửa `ci.yml` job `python-tests` cài `windows/requirements-dev.txt` + `spikes/requirements-ci.txt`. Commit `feat(windows): config loading`.

### Task 2: OCR có toạ độ

**Files:**
- Create: `windows/app/ocr/__init__.py`, `windows/app/ocr/base.py`, `windows/app/ocr/windows_ocr.py`
- Test: `windows/tests/test_windows_ocr.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Line(text: str, left: float, top: float, width: float, height: float)` + thuộc tính `right`, `bottom`.
  - `class OcrUnavailable(Exception)` (thông điệp chứa hướng dẫn `Settings > Time & language > Language`).
  - `class OcrEngine(Protocol): def recognize(self, img: PIL.Image.Image) -> list[Line]`.
  - `class WindowsOcr(OcrEngine)`: `__init__(lang: str = "en", min_height: int = 32)`; ảnh chuyển RGB (bỏ alpha, nền trắng), cao < `min_height` thì phóng to giữ tỉ lệ và **toạ độ trả về theo ảnh gốc** (chia lại tỉ lệ). Toạ độ dòng = khung bao các `words[*].bounding_rect`. Chỉ lỗi khi tạo/gọi engine với ngôn ngữ → `OcrUnavailable`; lỗi khác giữ nguyên.

- [ ] **Step 1:** Viết test: (a) `@local`: ảnh 600×80 nền đen chữ trắng "Hello world" (Segoe UI 40) → 1 `Line`, text chứa "Hello world", `0 <= left < 50`, `height > 20`; (b) `@local`: ảnh 300×16 RGBA → không lỗi, toạ độ trả về nằm trong 300×16; (c) monkeypatch `winocr.recognize_pil_sync` ném lỗi → `OcrUnavailable` chứa `"Language"`; (d) `@local` dùng `spikes/ocr/data/rv_02_short.png` nếu có (skip nếu không): 2 dòng, dòng 2 là `"A nightmare overly real."`, dòng 1 nằm trên dòng 2.
- [ ] **Step 2:** Chạy → FAIL. **Step 3:** Implement. **Step 4:** Chạy → PASS.
- [ ] **Step 5:** Commit `feat(windows): windows ocr with line boxes`.

### Task 3: Hậu xử lý + fixtures dùng chung

**Files:**
- Create: `windows/app/text/__init__.py`, `windows/app/text/postprocess.py`
- Create: `shared/fixtures/postprocess/*.json` (≥ 8 file), `shared/fixtures/postprocess/README.md` (định dạng)
- Test: `windows/tests/test_postprocess.py`

**Interfaces:**
- Consumes: `Line` (Task 2).
- Produces:
  - `@dataclass Paragraph(kind: Literal["name", "text"], text: str, sentences: list[str], left, top, right, bottom: float)`.
  - `postprocess(lines: list[Line]) -> list[Paragraph]` — thứ tự trên→dưới, trái→phải.
  - `split_sentences(text: str) -> list[str]`.
- Fixture JSON: `{"name": str, "lines": [{"text": str, "box": [left, top, width, height]}], "expected": [{"kind": "name"|"text", "text": str, "sentences": [str, ...]}]}`.

Quy tắc (chốt ở đây để Kotlin làm giống hệt):
1. Bỏ dòng không có chữ cái nào, hoặc chỉ 1 ký tự sau khi strip.
2. Sắp theo `top` rồi `left`. `h` = trung vị chiều cao dòng. Một dòng **nối vào đoạn hiện tại** khi `line.top - para.bottom <= 0.6*h` **và** `line.left` trong `[para.left - h, para.right]`; ngược lại mở đoạn mới (các dòng cùng hàng nhưng cách xa ngang → đoạn khác nhau).
3. Nối dòng bằng 1 dấu cách; dòng kết thúc `[a-z]-` và dòng sau bắt đầu chữ thường → nối liền, bỏ gạch nối.
4. **Tên:** đoạn 1 dòng, ≤ 3 từ, mỗi từ bắt đầu chữ hoa hoặc là số La Mã, **và** (kết thúc bằng `:` **hoặc** không có dấu câu cuối và có một đoạn khác nằm ngay dưới trong khoảng `2*h`) → `kind="name"`, bỏ `:` cuối. Trong đoạn tên, token khớp `^[Il1|]{2,4}$` → `"I" * len` (sửa "Druvis Ill" → "Druvis III").
5. Chuẩn hóa khoảng trắng.
6. Tách câu (đoạn `text`): sau `[.!?…]+` (kèm `"”’'` đóng tùy chọn) + khoảng trắng + chữ hoa hoặc `"“`; **không** tách sau `Mr. Mrs. Ms. Dr. St. vs. etc.` và sau một chữ cái hoa đứng một mình + `.`. `"Vertin ... was"` (sau là chữ thường) không tách.

- [ ] **Step 1:** Viết fixtures (box lấy từ OCR thật của ảnh Phase 0 khi có, còn lại tự đặt): `name_two_lines` (rv_01: tên + 2 dòng → name "Druvis III" + text 2 câu), `name_roman_ill` (tên OCR "Druvis Ill" → "Druvis III"), `narration_no_name` (rv_05: 1 đoạn 2 câu, có `she's`), `log_colon_names` (rv_06: "Druvis III:" cùng hàng với câu, cách xa ngang → name + text riêng; "Vertin ... was the first to leave." 1 câu), `hyphenation` (`informa-` / `tion is key.` → `information is key.`), `junk_lines` (`▼`, `123`, `—` bị bỏ), `two_paragraphs_gap` (khoảng cách dọc 2h → 2 đoạn), `abbrev_and_ellipsis` (`Mr. Smith left. Then... nothing.` → 2 câu: `Mr. Smith left.`, `Then... nothing.`), `ui_buttons_row` (`AUTO`, `SKIP`, `EXIT` cùng hàng, cách xa → 3 đoạn text riêng).
- [ ] **Step 2:** Test tham số hóa đọc mọi file trong `shared/fixtures/postprocess/`: `[(p.kind, p.text, p.sentences) for p in postprocess(lines)] == expected`; thêm test `split_sentences` cho các ví dụ quy tắc 6. Chạy → FAIL.
- [ ] **Step 3:** Implement. **Step 4:** Chạy → PASS. **Step 5:** Commit `feat(windows): postprocess with shared fixtures`.

### Task 4: Bảng thuật ngữ

**Files:**
- Create: `windows/app/glossary.py`, `shared/schemas/glossary.schema.json`, `shared/glossary/common.json`, `shared/glossary/games/reverse1999.json`, `shared/glossary/common_words_en.txt` (sinh bằng script), `shared/glossary/make_common_words.py`
- Test: `windows/tests/test_glossary.py`

**Interfaces:**
- Produces:
  - Glossary JSON: `{"version": 1, "entries": [{"source": str, "type": "keep"|"map", "target": str (bắt buộc khi map), "case_sensitive": bool (mặc định true)}]}`.
  - `class Glossary`: `Glossary.load(*paths: Path) -> Glossary` (thứ tự tham số = ưu tiên cao → thấp: game, rồi chung); `add_keep(term: str)`; `protect(text: str) -> tuple[str, list[str]]` trả text đã thay placeholder và danh sách giá trị thay lại (`keep` → chính `source`, `map` → `target`); `restore(text: str, values: list[str]) -> str | None` (None nếu thiếu/thừa/hỏng placeholder).
  - `PLACEHOLDER: str` — format chọn ở Step 5, dùng `.format(i=...)`.
  - `class ProperNounTracker(common_words: set[str], min_count: int = 3)`: `observe(sentence: str) -> list[str]` trả các từ **vừa** đạt ngưỡng (viết hoa, không đứng đầu câu, ≥ `min_count` lần, chữ thường của nó không thuộc `common_words`).
- Khớp thuật ngữ: dài nhất trước, theo ranh giới từ (`\b`), không khớp chồng.

- [ ] **Step 1:** `make_common_words.py`: `wordfreq.top_n_list("en", 5000)` → `common_words_en.txt` (1 từ/dòng). Chạy, commit file. `common.json`: `keep` cho `HP MP SP AP ATK DEF DMG EXP CD UI`. `reverse1999.json`: `keep` `Vertin`, `Sonetto`, `Druvis III`, `Timekeeper`, `Madam Z`, `Sotheby`.
- [ ] **Step 2:** Test: protect/restore vòng tròn với `keep` và `map`; ưu tiên game > chung (cùng `source`, game thắng); dài nhất trước (`Druvis III` không bị tách thành `Druvis`); `case_sensitive` false; restore trả `None` khi placeholder bị xóa / bị đổi số; schema hợp lệ cho cả 2 file JSON (jsonschema); `ProperNounTracker`: "Hello Bob." ×3 → lần 3 trả `["Bob"]`, "The" đầu câu không tính, "Water" (thuộc từ thông dụng) không tính.
- [ ] **Step 3:** Chạy → FAIL. **Step 4:** Implement. Chạy → PASS.
- [ ] **Step 5 (chọn placeholder, `@local`, cần model vinai sau Task 6 — làm Step này sau Task 6):** test `test_placeholder_survives_vinai` dịch 10 câu chứa 1–2 thuật ngữ (dùng `reverse1999.json`) qua `Ct2Translator`; thử lần lượt `"⟦{i}⟧"`, `"[{i}]"`, `"ZQX{i}"`, chọn **mẫu đầu tiên giữ nguyên ≥ 9/10 câu**, gán vào `PLACEHOLDER`, test khẳng định ≥ 9/10 với mẫu đã chọn. Ghi số liệu vào commit message.
- [ ] **Step 6:** Commit `feat(windows): glossary with placeholders and proper-noun tracking`.

### Task 5: Cache + nhật ký cặp dịch

**Files:**
- Create: `windows/app/cache.py`, `windows/app/datalog.py`
- Test: `windows/tests/test_cache.py`

**Interfaces:**
- Produces:
  - `normalize(text: str) -> str` (gộp khoảng trắng, strip).
  - `class TranslationCache(max_items: int, db_path: Path | None)`: `get(model_id: str, text: str) -> str | None`, `put(model_id, text, translation)`, `close()`. LRU trong bộ nhớ (`OrderedDict`); có `db_path` → SQLite bảng `translations(model TEXT, src TEXT, tgt TEXT, PRIMARY KEY(model, src))`, đọc lại khi mở.
  - `class PairLogger(path: Path, enabled: bool)`: `log(source, translation, model_id, game: str | None)` ghi 1 dòng JSON UTF-8 (`ensure_ascii=False`) vào `translations.jsonl`.
- [ ] **Step 1:** Test: get sau put; key chuẩn hóa khoảng trắng; khác `model_id` không lẫn; vượt `max_items` → mục cũ nhất bị loại; persist: put → close → mở lại cùng `db_path` → get được; `PairLogger` disabled không tạo file; enabled ghi tiếng Việt đọc lại đúng.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): translation cache and pair log`.

### Task 6: Translator CTranslate2

**Files:**
- Create: `windows/app/translate/__init__.py`, `windows/app/translate/base.py`, `windows/app/translate/ct2.py`, `windows/tests/fakes.py`
- Modify: `models/export.py` (ghi `screentrans_model.json` cạnh model), `models/tests/test_verify.py` (test hàm sinh meta)
- Test: `windows/tests/test_translator.py`

**Interfaces:**
- Produces:
  - `class Translator(Protocol): model_id: str; def translate(self, texts: list[str]) -> list[str]`.
  - `screentrans_model.json`: `{"id": str, "kind": "marian"|"mbart", "format": "ct2"|"onnx", "src_lang": str|null, "tgt_prefix": str|null}`; `models.export.model_meta(key: str, fmt: str) -> dict`.
  - `class ModelNotFound(Exception)` (thông điệp nêu đường dẫn và lệnh `python -m models.export ct2 <id>`).
  - `class Ct2Translator(Translator)`: `__init__(model_dir: Path, beam_size: int = 2, intra_threads: int = 2)`; đọc meta; `translate` dịch **một batch**, `max_input_length=512`, `max_decoding_length=256`, mBART dùng `target_prefix` và bỏ token tiền tố khỏi kết quả; chuỗi rỗng/blank → `""` không gửi model; `warm_up() -> float` (ms).
  - `windows/tests/fakes.py`: `FakeTranslator(fn: Callable[[str], str], model_id="fake")` ghi lại các batch đã nhận (`calls: list[list[str]]`).
- [ ] **Step 1:** Test `models`: `model_meta("vinai-en2vi","ct2") == {"id":"vinai-en2vi","kind":"mbart","format":"ct2","src_lang":"en_XX","tgt_prefix":"vi_VN"}`. Test windows: thư mục không có `model.bin` → `ModelNotFound`; `@local` (skip nếu chưa export): vinai dịch `["We have to leave right now.", "", "Good morning, Timekeeper."]` → 3 kết quả, kết quả 2 là `""`, không chứa `vi_VN`; câu 600 token không lỗi và trả chuỗi không rỗng; `warm_up()` trả số > 0.
- [ ] **Step 2:** FAIL. **Step 3:** Implement; chạy lại `python -m models.export ct2 vinai-en2vi` và `opus-mt-en-vi` để có meta. **Step 4:** PASS. **Step 5:** Commit `feat(windows): ctranslate2 translator`.
- [ ] **Step 6:** Quay lại làm Task 4 Step 5 (chọn placeholder).

### Task 7: Pipeline

**Files:**
- Create: `windows/app/pipeline.py`
- Test: `windows/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `OcrEngine`, `postprocess`, `Glossary`, `ProperNounTracker`, `TranslationCache`, `PairLogger`, `Translator`.
- Produces:
  - `@dataclass Segment(kind: Literal["name","text"], source: str, translation: str | None, box: tuple[float, float, float, float])` (`translation` là `None` với `name`).
  - `@dataclass PipelineResult(segments: list[Segment], timings_ms: dict[str, float])` — khóa timings: `ocr`, `postprocess`, `translate`, `total`.
  - `class Pipeline(ocr, translator, glossary, cache, tracker=None, pair_logger=None, game: str | None = None)`: `run(img) -> PipelineResult`; `translate_paragraphs(paragraphs: list[Paragraph]) -> list[Segment]` (dùng lại cho GUI).
- Thuật toán `translate_paragraphs`: gom mọi câu của mọi đoạn `text` → câu có trong cache dùng luôn → câu còn lại: `protect` → **một** lời gọi `translator.translate` → `restore`; câu nào `restore` trả `None` → gom lại dịch **một lời gọi nữa không placeholder** → `cache.put` + `pair_logger.log` → ghép câu đã dịch của mỗi đoạn bằng dấu cách. Tracker `observe` mọi câu; từ mới đạt ngưỡng → `glossary.add_keep`.
- [ ] **Step 1:** Test (dùng `FakeTranslator` + OCR giả trả `Line` cố định): tên không bị dịch; 2 đoạn 3 câu → translator nhận **đúng 1 batch** 3 câu; chạy lại cùng ảnh → translator không được gọi (cache); translator giả xóa placeholder → câu đó được dịch lại không placeholder, `translation` không `None`; tracker: từ "Bob" xuất hiện 3 lần → lần sau được giữ nguyên qua placeholder; `timings_ms` có đủ 4 khóa; ảnh không chữ → `segments == []`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): translation pipeline`.

### Task 8: Chụp màn hình

**Files:**
- Create: `windows/app/capture.py`
- Test: `windows/tests/test_capture.py`

**Interfaces:**
- Produces: `enable_dpi_awareness() -> None` (gọi `SetProcessDpiAwareness(2)`, bỏ qua nếu đã đặt/không hỗ trợ); `capture_region(left: int, top: int, width: int, height: int) -> PIL.Image.Image` (toạ độ **pixel vật lý** của màn hình ảo, dùng `mss`, trả RGB); `parse_region(s: str) -> tuple[int, int, int, int]` cho chuỗi `"x,y,w,h"` (w,h > 0, lỗi → `ValueError` có thông điệp).
- [ ] **Step 1:** Test: `parse_region("10,20,300,40") == (10,20,300,40)`; `"10,20,0,40"` và `"a,b"` → `ValueError`; `@local`: `capture_region(0,0,120,50).size == (120,50)` và mode `RGB`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): screen capture`.

### Task 9: CLI

**Files:**
- Create: `windows/app/cli.py`, `windows/app/__main__.py` không cần (dùng `python -m app.cli`)
- Test: `windows/tests/test_cli.py`

**Interfaces:**
- Consumes: mọi module trên; `ensure_model` (Task 10) — trước khi Task 10 xong, chỉ hỗ trợ `--model-dir`.
- Produces: `main(argv: list[str] | None = None) -> int`. Tham số: `--image PATH` | `--screen x,y,w,h` (bắt buộc một trong hai), `--config PATH` (mặc định `windows/config.yaml` cạnh package), `--model-dir DIR`, `--glossary PATH` (lặp được, thêm sau bảng chung), `--show-source`, `--json`, `--timings`.
- Đầu ra mặc định: mỗi segment một khối — tên in `[Druvis III]`; text in bản dịch (với `--show-source` thêm dòng `EN: ...` trước). `--json`: `{"segments": [...], "timings_ms": {...}}` (UTF-8, `ensure_ascii=False`). `--timings`: in timings ra **stderr**.
- Mã thoát: 0 thành công (kể cả không có chữ → in `(không tìm thấy chữ)`); 2 thiếu model (`ModelNotFound`, in thông điệp); 3 OCR không khả dụng (`OcrUnavailable`); 4 tham số sai.
- **Đầu tiên trong `main`:** `sys.stdout.reconfigure(encoding="utf-8")` và tương tự `stderr`.
- [ ] **Step 1:** Test (monkeypatch để `main` dùng OCR giả + `FakeTranslator` qua một hook `build_pipeline` có thể thay): in `[Druvis III]` và bản dịch; `--json` parse được, có `segments`; ảnh trắng → `(không tìm thấy chữ)`, mã 0; `--model-dir` không tồn tại → mã 2; thiếu cả `--image` và `--screen` → mã 4; **subprocess** chạy `windows/tests/cli_fake_runner.py` (script test: thay `build_pipeline` bằng OCR giả + `FakeTranslator` trả `"Xin chào"`, rồi gọi `main`) với env đã **xóa** `PYTHONIOENCODING` và `PYTHONUTF8` → stdout (giải mã UTF-8) chứa `"Xin chào"`, không `UnicodeEncodeError` — không thêm hook test nào vào code sản phẩm; `@local` end-to-end: `--image spikes/ocr/data/rv_02_short.png --model-dir models/out/vinai-en2vi-ct2` → mã 0, có `[Druvis III]`, có ít nhất một ký tự tiếng Việt có dấu.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): cli`.

### Task 10: Manifest + tải model + workflow `models.yml`

**Files:**
- Create: `windows/app/models.py`, `models/manifest.py`, `shared/schemas/model-manifest.schema.json`, `.github/workflows/models.yml`
- Modify: `windows/app/cli.py` (khi không có `--model-dir` → `ensure_model`)
- Test: `windows/tests/test_models.py`, `models/tests/test_manifest.py`

**Interfaces:**
- Produces:
  - Manifest: `{"version": 1, "models": [{"id": str, "platform": "windows"|"android", "format": "ct2"|"onnx", "version": str, "license": str, "files": [{"path": str, "url": str, "sha256": str, "size": int}]}]}`.
  - `models.manifest.build_manifest(export_dirs: dict[str, Path], base_url: str, version: str, licenses: dict[str, str]) -> dict` (`url` = `{base_url}/{id}/{version}/{path}`); CLI `python -m models.manifest --base-url URL --version V out.json`.
  - `app.models.ensure_model(model_id: str, manifest_url: str, data_dir: Path, platform="windows", progress: Callable[[int,int],None] | None = None) -> Path`: đã có đủ file đúng size → trả thư mục `data_dir/models/<id>/<version>/` (không tải lại); thiếu → tải từng file vào `*.part`, kiểm SHA-256, đúng thì đổi tên, sai → xóa `.part` và ném `ModelDownloadError` (nêu file + hướng dẫn thử lại); không có model id trong manifest → `ModelNotFound`; mạng lỗi → `ModelDownloadError` có hướng dẫn dùng `--model-dir`.
- `models.yml` (`workflow_dispatch`, input `hf_repo`, `version`): cài `models/requirements.txt` + torch CPU, export `ct2` cho `vinai-en2vi` và `opus-mt-en-vi`, `onnx` cho `opus-mt-en-vi`, chạy `models.verify`, sinh manifest (license đọc từ model card: điền đúng giấy phép từng model — kiểm tra trên trang HF khi viết), upload bằng `huggingface_hub.upload_folder` với secret `HF_TOKEN`.
- [ ] **Step 1:** Test với `http.server` cục bộ trong thread phục vụ thư mục tạm: tải đủ → file đúng nội dung; gọi lần 2 không request lại (đếm request); sửa SHA trong manifest → `ModelDownloadError`, không còn file `.part` hay file đích; id lạ → `ModelNotFound`; `build_manifest` cho ra JSON hợp lệ theo schema, SHA đúng.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** CLI: không `--model-dir` → `ensure_model(config.translator.model, config.models.manifest_url, config.paths.data_dir)` (in tiến trình ra stderr). **Step 6:** Commit `feat: model manifest, downloader, models workflow`.
- [ ] **Step 7 — dừng, nhờ người dùng:** tạo tài khoản/repo model public trên Hugging Face, tạo token ghi, thêm secret `HF_TOKEN` vào GitHub, chạy workflow `models` với `hf_repo`; cập nhật `models.manifest_url` trong `config.yaml`. (Không chặn Task 11.)

### Task 11: Benchmark + tài liệu

**Files:**
- Create: `windows/scripts/benchmark.py`
- Modify: `AGENT.md` (tick Phase 1, ghi số đo), `README.md` (cách dùng CLI)

**Interfaces:**
- Consumes: `Pipeline`, `Ct2Translator`, `WindowsOcr`.
- Produces: `python windows/scripts/benchmark.py --model-dir DIR [--images GLOB]` (mặc định `spikes/ocr/data/rv_*.png`): in thời gian load + warm-up, rồi mỗi ảnh: ocr / postprocess / translate / total (ms, trung vị 3 lần, **xóa cache giữa các lần**), dòng tổng kết so với ngân sách **Live < 400 ms** (1–2 câu) và ghi `windows/out/benchmark.json`.
- [ ] **Step 1:** Chạy benchmark cho vinai và opus → Expected: bảng in ra; ghi số liệu.
- [ ] **Step 2:** Cập nhật `AGENT.md` mục 15 Phase 1 (tick + số đo), `README.md` (cài đặt, `python -m app.cli --image ...`, `--screen`, `--glossary`).
- [ ] **Step 3:** Chạy toàn bộ `pytest -q` → Expected: pass. Commit `docs: phase 1 benchmark and usage`; push nhánh `phase-1`, nhờ người dùng xác nhận CI xanh.
