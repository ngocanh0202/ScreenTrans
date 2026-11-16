# ScreenTrans — OCR màn hình & dịch Anh → Việt khi chơi game (Windows + Android)

> Đặc tả để **Claude Code** triển khai. Thiết kế đầy đủ và lý do các quyết định: [docs/superpowers/specs/2026-11-16-screentrans-design.md](docs/superpowers/specs/2026-11-16-screentrans-design.md). Làm lần lượt theo Phase; mỗi Phase phải chạy được, có test, và báo cáo benchmark trước khi sang Phase tiếp.

## 1. Mục tiêu

Vừa chơi game vừa đọc bản dịch tiếng Việt của chữ tiếng Anh trên màn hình, độ trễ thấp, **chạy hoàn toàn trên thiết bị** (offline), trên **Windows 10/11** và **Android**.

- **Live:** chọn khung thoại một lần → app tự dịch mỗi khi chữ đổi (game kiểu visual novel như Reverse: 1999, phụ đề, hội thoại NPC).
- **Một lần:** phím tắt (Windows) / nút nổi (Android) → chọn vùng bất kỳ → dịch (mô tả vật phẩm, nhiệm vụ, menu).
- Dùng được cho **nhiều game**: hồ sơ theo game tự nhận, bảng thuật ngữ tự lớn dần.

**Thất bại nếu:** game giật/tụt FPS; cần mạng mới dịch được; game mới phải cấu hình nhiều; bản dịch hiện khi câu thoại đã qua.

## 2. Phạm vi

- Nguồn: **chỉ tiếng Anh** (kiến trúc cho phép thêm ngôn ngữ sau: mỗi model = một cặp ngôn ngữ → Việt). Đích: tiếng Việt.
- Nền tảng: Windows + Android. Các nền tảng khác làm sau.
- Không cần: đăng nhập, cloud, đồng bộ, API dịch online.

## 3. Thiết bị mục tiêu & ràng buộc

- Laptop: GTX 1650 Ti 4 GB VRAM, 16 GB RAM → **không dùng GPU cho OCR/dịch** (để dành cho game). Dịch chạy CPU, int8, giới hạn luồng.
- Điện thoại: POCO X8 Pro → dịch trên máy bằng CPU, 2 luồng.
- Không gọi API dịch online. Kaggle **chỉ** dùng để fine-tune, không dùng để phục vụ dịch.
- File cài đặt không chứa model; model tải lần đầu từ repo model public trên Hugging Face Hub.
- Chỉ dùng cá nhân; không cần ký code Windows.
- Game Windows chạy **cửa sổ / borderless**. Fullscreen độc quyền không hỗ trợ (không hook DirectX); phát hiện được thì hiện hướng dẫn đổi sang borderless.
- Android minSdk 29, target SDK mới nhất.

## 4. Tech stack

| Thành phần | Windows | Android |
|---|---|---|
| Ngôn ngữ | Python 3.11 | Kotlin |
| UI / overlay | PySide6 (frameless, always-on-top, tray) | View overlay `TYPE_APPLICATION_OVERLAY`, nút nổi |
| Chụp màn hình | `mss` (đa màn hình, DPI) | MediaProjection (foreground service) |
| OCR chính | Windows OCR qua `winocr` | ML Kit Text Recognition (Latin, bundled) |
| OCR dự phòng | RapidOCR (model PaddleOCR trên onnxruntime) | — |
| Dịch | CTranslate2 int8 CPU + tokenizer `transformers`/`sentencepiece` | ONNX Runtime int8 (encoder + decoder có KV-cache) + SentencePiece |
| Phím tắt | `keyboard` hoặc `pynput` | — |
| Cấu hình | `config.yaml` | DataStore |
| Hồ sơ game, thuật ngữ | JSON theo schema trong `shared/` | cùng schema |
| Test | `pytest` | JUnit (`./gradlew test`) |
| Đóng gói | PyInstaller `--noconsole` | Gradle `assembleRelease`, ký bằng keystore |
| CI/CD | GitHub Actions | GitHub Actions |

## 5. Cấu trúc repo (monorepo)

```
screentrans/
├── README.md
├── AGENT.md
├── docs/superpowers/specs/      # thiết kế
├── shared/
│   ├── schemas/                 # profile.schema.json, glossary.schema.json, model-manifest.schema.json
│   ├── glossary/common.json     # thuật ngữ chung (HP, MP, Buff, Quest...)
│   └── fixtures/postprocess/    # input dòng OCR → output kỳ vọng; cả Python và Kotlin phải pass
├── windows/
│   ├── requirements.txt
│   ├── config.yaml
│   ├── app/
│   │   ├── main.py              # tray + hotkey + vòng đời
│   │   ├── cli.py               # python -m app.cli --image sample.png
│   │   ├── config.py
│   │   ├── capture.py           # mss, DPI
│   │   ├── selector.py          # kéo chọn vùng
│   │   ├── overlay.py           # overlay bản dịch (tương tác + click-through)
│   │   ├── live.py              # phát hiện thay đổi + chờ chữ ổn định
│   │   ├── profiles.py          # hồ sơ game, nhận game theo process foreground
│   │   ├── glossary.py          # placeholder, tên riêng tự động, ghi sửa
│   │   ├── models.py            # tải model theo manifest, kiểm SHA-256
│   │   ├── cache.py             # LRU + SQLite
│   │   ├── ocr/{base,windows_ocr,rapid_ocr}.py
│   │   ├── text/postprocess.py
│   │   └── translate/{base,ct2_marian,ct2_mbart}.py
│   ├── scripts/benchmark.py
│   └── tests/
├── android/                     # dự án Gradle (app module Kotlin)
├── models/
│   ├── export.py                # HF → CT2 int8 (Windows) + ONNX int8 (Android), tạo manifest.json
│   └── verify.py                # so output CT2/ONNX với transformers gốc
├── training/
│   └── kaggle_finetune.ipynb    # Phase 6
└── .github/workflows/
    ├── ci.yml
    ├── build-windows.yml
    ├── build-android.yml
    ├── release.yml
    └── models.yml
```

## 6. Luồng xử lý (chung hai nền tảng)

```
Chụp vùng → [Live: phát hiện thay đổi → chờ chữ ổn định] → OCR → hậu xử lý
→ bảo vệ thuật ngữ (placeholder) → cache → dịch batch → khôi phục thuật ngữ → overlay
```

## 7. Engine dịch

Interface: `Translator.translate(list[str]) -> list[str]` — luôn dịch **theo batch**. Model load **một lần**, chạy trên thread riêng, chỉ chạy khi có chữ mới.

| Model | Ghi chú |
|---|---|
| `Helsinki-NLP/opus-mt-en-vi` (Marian, ~75M) | Nhanh, dự kiến mặc định Android |
| `vinai/vinai-translate-en2vi-v2` (mBART) | Chất lượng cao, dự kiến mặc định Windows. Tokenizer `src_lang="en_XX"`, decode với `target_prefix=[["vi_VN"]]`. **Bắt buộc** `models/verify.py` so output CT2/ONNX với `transformers` gốc. |

- **Model mặc định mỗi nền tảng chốt bằng benchmark** theo ngân sách ở mục 13: dùng vinai nếu đạt, không thì opus-mt.
- `beam_size` cấu hình được (mặc định 2). Windows: `intra_threads=2`, `inter_threads=1`.
- Thiếu model → app hiện màn hình tải model (không crash).

## 8. Hậu xử lý văn bản (`postprocess`)

1. Sắp xếp dòng (trên→dưới, trái→phải), nhóm **đoạn** theo khoảng cách dọc.
2. Nối dòng trong đoạn; sửa gạch nối cuối dòng (`informa-` + `tion` → `information`).
3. **Tách tên nhân vật:** nếu hồ sơ có vùng `name` thì dùng vùng đó; nếu không, dòng đầu ngắn (≤ 3 từ, viết hoa chữ đầu, không có dấu câu cuối) tách biệt phía trên → là tên, không dịch.
4. **Câu lựa chọn:** mỗi khối tách biệt trong vùng `choices` dịch riêng, giữ thứ tự.
5. Tách câu (regex hoặc `pysbd`), làm sạch ký tự rác, bỏ dòng chỉ có ký hiệu/số.
6. Sau khi dịch, ghép câu lại theo đoạn.

Test bằng fixtures trong `shared/fixtures/postprocess/`: nhiều đoạn, gạch nối, dòng rác, câu qua nhiều dòng, dòng tên, nhiều lựa chọn. Bản Kotlin phải pass cùng fixtures.

## 9. Bảng thuật ngữ

- Ba lớp, ưu tiên từ trên xuống: **theo game** → **tự động (tên riêng)** → **chung**.
- Loại mục: `keep` (giữ nguyên) và `map` (bản dịch cố định).
- Trước khi dịch thay thuật ngữ bằng placeholder (`⟦0⟧`, `⟦1⟧`…), sau khi dịch khôi phục. Nếu placeholder bị hỏng trong output → dịch lại câu đó không dùng placeholder.
- **Tên riêng tự động:** từ viết hoa không đứng đầu câu, xuất hiện ≥ 3 lần trong phiên, không thuộc danh sách từ tiếng Anh thông dụng → thêm `keep` vào lớp tự động (người dùng xem/xóa được).
- **Sửa từ overlay**, hai thao tác:
  - **Sửa cả câu** → lưu vào `overrides` của hồ sơ game (câu nguồn chuẩn hóa → bản dịch người dùng), lần sau dùng luôn, không qua model; ghi thêm `corrections.jsonl`.
  - **Đánh dấu từ/cụm từ** trong câu gốc → `keep` hoặc `map` → thêm vào bảng thuật ngữ của game.
- Thứ tự áp dụng: `overrides` → cache → thuật ngữ + model.

## 10. Hồ sơ game

- Mỗi game một file JSON (schema `shared/schemas/profile.schema.json`): định danh (Windows: tên exe; Android: package name), vùng `dialogue` / `name` / `choices` (tùy chọn), engine OCR, `interval_ms`, `settle_ms`, `change_threshold`, đường dẫn bảng thuật ngữ.
- Tọa độ vùng lưu **tương đối (0–1) theo cửa sổ game** (Windows) / màn hình (Android) để không lệch khi đổi độ phân giải, DPI, xoay màn hình.
- Tự nhận game: Windows theo process của cửa sổ foreground; Android theo `UsageStatsManager` (thiếu quyền → cho chọn tay).
- Game chưa có hồ sơ → tạo mặc định khi người dùng chọn vùng lần đầu.

## 11. Chế độ Live & overlay

- Chụp mỗi `interval_ms` (mặc định 300). So ảnh thu nhỏ grayscale (rộng 64 px, sai khác trung bình) với lần trước; dưới `change_threshold` → bỏ qua.
- Có thay đổi → đợi đến khi ảnh đứng yên `settle_ms` (mặc định 250) rồi mới OCR (xử lý chữ hiện dần).
- Text giống lần trước → không dịch. Câu đã có → lấy từ cache.
- Overlay Live **click-through** (Windows `WS_EX_TRANSPARENT`; Android `FLAG_NOT_TOUCHABLE`), có nút nhỏ tạm ẩn / chuyển sang chế độ tương tác để sửa bản dịch.
- **Overlay đặt cạnh khung thoại, không che chữ gốc** (mặc định phía trên, tràn thì đặt dưới) và **không bao giờ nằm trong vùng chụp** (tránh OCR chính bản dịch). Windows thêm `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`. Android: nếu buộc phải chồng thì cắt vùng chụp tránh phần overlay.
- Overlay chung: nền tối bán trong suốt, chữ trắng, font hỗ trợ tiếng Việt (Windows: Segoe UI), cỡ chữ và độ trong cấu hình được, tùy chọn hiện bản gốc song song.
- Windows một lần: `Ctrl+Alt+T` chọn vùng → overlay (Esc / click ngoài để đóng, nút copy, nút sửa). `Ctrl+Alt+L` bật/tắt Live. Tray: bật/tắt Live, đổi engine OCR/dịch, mở cài đặt, thoát.
- Android: nút nổi — chạm để dịch vùng Live hiện tại, giữ để kéo chọn vùng mới; thông báo foreground service có nút dừng.
- Xử lý đúng DPI scaling (125%, 150%) và nhiều màn hình trên Windows.

## 12. Cache, dữ liệu, model

- Cache LRU (key = câu đã chuẩn hóa + model id) + SQLite giữ giữa các lần chạy.
- Ghi `translations.jsonl` (gốc, dịch, model, game) và `corrections.jsonl` — có thể tắt trong cấu hình.
- Model đăng trên **repo model public ở Hugging Face Hub** (repo code private nên không dùng Release để chứa model), kèm `manifest.json` (tên, nền tảng, định dạng, URL, SHA-256, kích thước, phiên bản). App đọc manifest từ URL cố định, tải lần đầu, kiểm SHA-256, lưu vào thư mục dữ liệu app. Kiểm tra giấy phép từng model trước khi đăng lại.

`windows/config.yaml` mẫu:

```yaml
hotkeys:
  translate_region: "ctrl+alt+t"
  toggle_live: "ctrl+alt+l"
ocr:
  engine: windows          # windows | rapid
translator:
  model: vinai-en2vi       # vinai-en2vi | opus-mt-en-vi (theo manifest)
  beam_size: 2
  intra_threads: 2
overlay:
  font_size: 14
  opacity: 0.85
  show_source: false
live:
  interval_ms: 300
  settle_ms: 250
  change_threshold: 5
cache:
  max_items: 5000
  persist: true
logging:
  save_pairs: true
models:
  manifest_url: "https://huggingface.co/<owner>/screentrans-models/resolve/main/manifest.json"
```

## 13. Ngân sách hiệu năng (tiêu chí nghiệm thu)

| Chỉ số | Windows | Android |
|---|---|---|
| Một lần: chọn vùng xong → hiện bản dịch (~50 từ) | < 500 ms | < 800 ms |
| Live: chữ ổn định → hiện bản dịch (1–2 câu) | < 400 ms | < 600 ms |
| CPU khi Live và màn hình không đổi | < 2% | không OCR/dịch |
| GPU dùng cho OCR/dịch | 0 | — |
| RAM thêm của app | < 1.5 GB | < 600 MB |
| FPS game | không giảm rõ rệt (đo trước/sau) | như Windows |

Ngoài ra: hiển thị đúng tiếng Việt có dấu; vùng không lệch ở 125%/150% DPI; mọi test pass trên CI.

## 14. CI/CD (GitHub Actions)

- `ci.yml` — mỗi push/PR: pytest (`windows-latest`), `./gradlew test`, fixtures dùng chung.
- `build-windows.yml` — PyInstaller `--noconsole` → artifact `.zip`.
- `build-android.yml` — `assembleRelease`, ký bằng keystore từ Secrets (`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`) → artifact `.apk`.
- `release.yml` — push tag `v*`: chạy hai build và đính kèm vào GitHub Release.
- `models.yml` — chạy tay: tải model HF, export CT2 int8 + ONNX int8, chạy `models/verify.py`, tạo manifest, upload lên repo model public trên HF Hub (secret `HF_TOKEN`).
- Repo GitHub do người dùng tạo (đề xuất private).

## 15. Các Phase

### Phase 0 — Khởi tạo & spike
- [ ] Cấu trúc monorepo, `.gitignore`, `ci.yml` khung chạy được.
- [ ] Spike A: `winocr` trên ảnh chụp thoại Reverse: 1999 (và thử RapidOCR) — đo độ chính xác, tốc độ. Thiếu gói English OCR thì in hướng dẫn cài.
- [ ] Spike B: vinai + opus-mt qua CT2 int8, so với `transformers` gốc (đặc biệt token ngôn ngữ mBART).
- [ ] Spike C: opus-mt ONNX int8 + tokenizer chạy trên Android (app thử tối thiểu), đo tốc độ trên POCO X8 Pro.

### Phase 1 — Lõi Windows (CLI)
- [ ] `capture`, `ocr/windows_ocr`, `text/postprocess`, `glossary`, `translate/*`, `cache`, `models`.
- [ ] `python -m app.cli --image sample.png` in bản dịch.
- [ ] Fixtures dùng chung + unit test. `scripts/benchmark.py` đo từng bước → chốt model mặc định Windows.
- [ ] `models.yml` + bản model đầu tiên trên HF Hub.

### Phase 2 — GUI Windows
- [ ] Tray + phím tắt toàn cục; `selector` (DPI, đa màn hình); `overlay` (copy, Esc, sửa).
- [ ] Model load trong worker thread, UI không đơ; màn hình tải model.
- [ ] `build-windows.yml`.

### Phase 3 — Live + hồ sơ game (Windows)
- [ ] `live` với phát hiện thay đổi + chờ ổn định + overlay click-through.
- [ ] `profiles` tự nhận game; tách tên / lựa chọn; tên riêng tự động; sửa bản dịch → thuật ngữ + `corrections.jsonl`.
- [ ] Đo FPS trước/sau. `release.yml`, phát hành `v0.1.0` Windows.

### Phase 4 — App Android
- [ ] MediaProjection foreground service, overlay + nút nổi, ML Kit OCR, ONNX dịch, postprocess (pass fixtures), thuật ngữ, cache, hồ sơ, Live.
- [ ] Tải model theo manifest. Đo ngân sách hiệu năng trên POCO X8 Pro → chốt model mặc định Android.
- [ ] `build-android.yml`, thêm `.apk` vào Release.

### Phase 5 — Hoàn thiện
- [ ] Màn hình cài đặt (cả hai nền tảng); xem/sửa bảng thuật ngữ; cập nhật model khi có manifest mới.

### Phase 6 — Fine-tune trên Kaggle (khi đã có dữ liệu sửa thật)
- [ ] Notebook `training/kaggle_finetune.ipynb`: GPU T4/P100, checkpoint định kỳ vào `/kaggle/working` (phiên tối đa 12 h, ~30 h GPU/tuần).
- [ ] Dữ liệu: PhoMT, IWSLT'15 en-vi, `corrections.jsonl` (upload làm Kaggle Dataset).
- [ ] Fine-tune `Seq2SeqTrainer`, `fp16=True`, tập con ~500k–1M cặp.
- [ ] Đánh giá sacreBLEU + COMET trên test PhoMT, so với model gốc. Chỉ thay nếu tốt hơn → export qua `models.yml`, cập nhật manifest trên HF Hub.

## 16. Ghi chú cho Claude Code

- Làm tuần tự theo Phase; cuối mỗi Phase chạy test + benchmark và báo cáo số liệu.
- Giữ code đơn giản; tách interface `OcrEngine` / `Translator` để dễ thay engine.
- Không gọi API dịch online. Không dùng GPU cho OCR/dịch.
- Khi không chắc về thư viện (`winocr`, token mBART với CT2, ONNX decoder trên Android), viết script/spike kiểm tra nhỏ trước khi tích hợp.
- Logic hậu xử lý: Python là bản chuẩn; mọi thay đổi phải cập nhật fixtures dùng chung trước.
