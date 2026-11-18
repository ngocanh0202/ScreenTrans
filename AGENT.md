# ScreenTrans — OCR màn hình & dịch Anh → Việt khi chơi game (Windows + Android)

> Đặc tả để **Claude Code** triển khai. Thiết kế đầy đủ và lý do các quyết định: [docs/superpowers/specs/2026-11-16-screentrans-design.md](docs/superpowers/specs/2026-11-16-screentrans-design.md). Làm lần lượt theo Phase; mỗi Phase phải chạy được, có test, và báo cáo benchmark trước khi sang Phase tiếp.

## 1. Mục tiêu

Vừa chơi game vừa đọc bản dịch tiếng Việt của chữ tiếng Anh trên màn hình, độ trễ thấp, **chạy hoàn toàn trên thiết bị** (offline), trên **Windows 10/11** và **Android**.

- **Live:** chọn khung thoại một lần → app tự dịch mỗi khi chữ đổi (game kiểu visual novel như Reverse: 1999, phụ đề, hội thoại NPC).
- **Một lần:** phím tắt (Windows) / nút nổi (Android) → chọn vùng bất kỳ → dịch (mô tả vật phẩm, nhiệm vụ, menu).
- Dùng được cho **nhiều game**: hồ sơ theo game tự nhận, bảng thuật ngữ tự lớn dần.

**Thất bại nếu:** game giật/tụt FPS; cần mạng mới dịch được; game mới phải cấu hình nhiều; bản dịch hiện khi câu thoại đã qua.

## 2. Phạm vi

- Nguồn mặc định: **tiếng Anh, dịch trên máy**. Ngôn ngữ khác (trước hết **tiếng Nhật**) dịch qua **engine từ xa trên Kaggle** (LLM). Đích: tiếng Việt.
- Kiến trúc đa ngôn ngữ từ đầu: hồ sơ game có `source_lang`; OCR, hậu xử lý, model chọn theo ngôn ngữ; manifest model ghi cặp ngôn ngữ.
- Nền tảng: Windows + Android. Các nền tảng khác làm sau.
- Không cần: đăng nhập, cloud, đồng bộ, API dịch online.

## 3. Thiết bị mục tiêu & ràng buộc

- Laptop: GTX 1650 Ti 4 GB VRAM, 16 GB RAM → **không dùng GPU cho OCR/dịch** (để dành cho game). Dịch chạy CPU, int8, giới hạn luồng.
- Điện thoại: POCO X8 Pro → dịch trên máy bằng CPU, 2 luồng.
- Không gọi API dịch online của bên thứ ba. Dịch **mặc định trên máy**. Kaggle dùng để fine-tune và làm **engine từ xa tùy chọn** (mục 7) — không bao giờ là đường bắt buộc.
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
│   │   └── translate/{base,ct2_marian,ct2_mbart,remote}.py
│   ├── scripts/benchmark.py
│   └── tests/
├── android/                     # dự án Gradle (app module Kotlin)
├── models/
│   ├── export.py                # HF → CT2 int8 (Windows) + ONNX int8 (Android), tạo manifest.json
│   └── verify.py                # so output CT2/ONNX với transformers gốc
├── training/
│   ├── kaggle_finetune.ipynb    # Phase 6
│   └── kaggle_serve.ipynb       # engine từ xa tùy chọn (Phase 5)
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
| `Helsinki-NLP/opus-mt-en-vi` (Marian, ~75M) | Nhanh. **Mặc định Android** (ONNX, CPU 2 luồng: 53 ms/câu trên POCO X8 Pro). Trên Windows là tùy chọn nhanh (CT2: ~250 ms/đoạn 50 từ) |
| `vinai/vinai-translate-en2vi-v2` (mBART) | **Mặc định Windows cho cả Live và phím tắt** (người dùng chọn 2026-11-17, ưu tiên chất lượng). CT2: ~260–300 ms/câu, ~1,2 s/đoạn 50 từ, 439 MB, +454 MB RAM. Tokenizer `src_lang="en_XX"`, decode với `target_prefix=[["vi_VN"]]`. **Bắt buộc** `models/verify.py` so output CT2/ONNX với `transformers` gốc. |

- **Model mặc định đã chốt sau Phase 0:** Windows = vinai (chấp nhận phím tắt dịch đoạn dài ~1–1,5 s, vượt ngân sách 500 ms ở mục 13 — ngân sách đó áp cho opus-mt); Android = opus-mt ONNX. Hiển thị "Đang dịch…" khi bản dịch mất > 300 ms.
- `beam_size` cấu hình được (mặc định 2). Windows: `intra_threads=2`, `inter_threads=1`.
- Thiếu model → app hiện màn hình tải model (không crash).
- Load model **ngầm ngay khi khởi động** (Android: khi bật foreground service), sau đó dịch một câu mẫu để làm nóng. Người dùng dịch khi chưa load xong → overlay hiện "Đang tải model…", có kết quả thì tự hiện. Benchmark ghi thêm thời gian load.

**Engine từ xa tùy chọn (`remote`)**
- Server: `training/kaggle_serve.ipynb` — load model trên GPU Kaggle (model đặt sẵn trong Kaggle Dataset để không tải lại mỗi phiên), FastAPI + ngrok. `POST /translate` `{"texts": [...], "source_lang": "ja", "context": [...], "glossary": {...}}` → `{"translations": [...]}`; `GET /health` (trả model đang chạy, ngôn ngữ hỗ trợ). Bắt buộc `Authorization: Bearer <token>` (token sinh khi chạy notebook).
- Model server mặc định: **LLM ~7B instruct lượng tử 4-bit qua vLLM** (dòng Qwen hoặc tương đương, chọn ở spike), prompt dịch sang tiếng Việt kèm vài câu thoại trước làm ngữ cảnh + thuật ngữ. Notebook có tùy chọn đổi sang LLM ~3B hoặc NLLB-200 3.3B (nhanh hơn). Spike: so 3 model trên cùng đoạn thoại game thật.
- Client (`translate/remote.py`, Kotlin tương ứng): URL + token trong cài đặt; **timeout theo ngôn ngữ**: `en` 1,5 s, `ja` 8 s (cấu hình được).
  - Ngôn ngữ **có** model local (en): lỗi/quá hạn → tự dùng model trên máy, overlay hiện chấm trạng thái, thử lại server sau 30 s.
  - Ngôn ngữ **không có** model local (ja): lỗi/quá hạn → overlay báo "Server dịch chưa bật / không phản hồi", thử lại sau 30 s.
- Chỉ khi bật remote thì text mới được gửi ra ngoài.

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

- Mỗi game một file JSON (schema `shared/schemas/profile.schema.json`): định danh (Windows: tên exe; Android: package name), `live.mode` (`dialogue` | `area`), vùng `dialogue` / `name` / `choices` / `area` (tùy chọn), engine OCR, `interval_ms`, `settle_ms`, `change_threshold`, đường dẫn bảng thuật ngữ.
- Tọa độ vùng lưu **tương đối (0–1) theo cửa sổ game** (Windows) / màn hình (Android) để không lệch khi đổi độ phân giải, DPI, xoay màn hình.
- Tự nhận game: Windows theo process của cửa sổ foreground; Android theo `UsageStatsManager` (thiếu quyền → cho chọn tay).
- Game chưa có hồ sơ → tạo mặc định khi người dùng chọn vùng lần đầu.

## 11. Chế độ Live & overlay

> **Cập nhật 2026-11-18 (người dùng chọn) — Live đè lên chữ gốc, dịch realtime từng câu.** Thay cho Live khung thoại (thẻ cạnh vùng) / Live vùng lớn ở trên:
> - Live có **hai phạm vi**: **Toàn màn hình** và **Vùng** (một hoặc nhiều vùng đã chọn). Cả hai **đè bản dịch lên đúng chỗ từng khối chữ gốc** (như chế độ toàn màn hình một lần), click-through. Bỏ kiểu thẻ đặt cạnh vùng. Thay quyết định cũ "không có Live toàn màn hình".
> - Cùng một cơ chế cho cả hai phạm vi: máy trạng thái chờ chữ + theo dõi khối (chỉ dịch khối mới/đổi, gỡ khối biến mất, tối đa `area_max_blocks`), OCR tối đa 1 lần / `area_min_interval_ms` khi màn hình động liên tục.
> - **Realtime từng câu:** khi chữ đang chạy, OCR mỗi `partial_interval_ms` (mặc định 500); câu nào đã **xong** (theo sau bởi câu khác, hoặc là câu cuối có `.`/`!`/`?`/`…` và giống hệt ở hai lần OCR liên tiếp) thì dịch và hiện ngay; câu đang gõ dở không hiện. Câu đã hiện không đổi nữa (trừ khi OCR đọc lại khác). Khi chữ dừng hẳn → dịch nốt phần còn lại (kể cả câu không có dấu kết thúc). Không dịch nháp từng chữ.
> - Android không loại overlay khỏi ảnh chụp được: ẩn lớp bản dịch ~0,2 s mỗi lần chụp OCR (nháy nhẹ). Người dùng chọn thử trước **chụp "Một ứng dụng"** (Android 14+, chọn game trong hộp thoại cấp quyền): nếu overlay không lọt vào ảnh thì không cần ẩn, không nháy; kiểm tra bằng mục "Kiểm tra chụp màn hình" và bỏ qua thay đổi do chính overlay gây ra.

- Máy trạng thái **ĐỨNG YÊN → ĐANG ĐỔI → ỔN ĐỊNH**:
  - ĐỨNG YÊN: chụp mỗi `interval_ms` (mặc định 300). So ảnh thu nhỏ grayscale (rộng 64 px, sai khác trung bình) với **ảnh ngay trước**; vượt `change_threshold` → ĐANG ĐỔI.
  - ĐANG ĐỔI: chụp mỗi `active_interval_ms` (mặc định 100); ảnh còn khác → đặt lại đồng hồ; không đổi đủ `settle_ms` (mặc định 250) → ỔN ĐỊNH. Quá `max_wait_ms` (mặc định 2000) vẫn chưa yên → coi như ỔN ĐỊNH.
  - ỔN ĐỊNH: OCR → nếu text mới bắt đầu bằng text OCR lần trước và dài hơn mà ảnh vẫn đổi (chữ đang chạy) thì quay lại ĐANG ĐỔI; nếu text giống bản đã dịch → không dịch; còn lại → dịch → ĐỨNG YÊN.
- **Live vùng lớn** (`live.mode: area` trong hồ sơ game, mặc định `dialogue`): cho game thoại **bong bóng** / chữ ở vị trí thay đổi. Người dùng chọn một vùng lớn; `ignore_regions` loại HUD. Cùng máy trạng thái chờ ổn định, nhưng OCR tối đa 1 lần mỗi `area_min_interval_ms` (1000). Nhóm khối chữ → so với khối đang hiển thị (text chuẩn hóa + vị trí gần) → **chỉ dịch khối mới/đổi**, gỡ overlay khối biến mất; tối đa `area_max_blocks` (30). Overlay đè đúng vị trí từng khối, click-through, không nằm trong ảnh chụp. Test bằng chuỗi khung hình giả lập: bong bóng mới xuất hiện, bong bóng cũ biến mất, nền động liên tục (≤ 1 OCR/s).
- Hồ sơ game có thể khai báo `ignore_regions` (vd góc có mũi tên ▼ nhấp nháy) — bị loại khỏi phép so ảnh.
- Test `live` bằng chuỗi khung hình giả lập: chữ chạy, bấm skip, mũi tên nhấp nháy, nền động liên tục, fade-in.
- Text giống lần trước → không dịch. Câu đã có → lấy từ cache.
- Overlay Live **click-through** (Windows `WS_EX_TRANSPARENT`; Android `FLAG_NOT_TOUCHABLE`), có nút nhỏ tạm ẩn / chuyển sang chế độ tương tác để sửa bản dịch.
- **Overlay đặt cạnh khung thoại, không che chữ gốc** (mặc định phía trên, tràn thì đặt dưới) và **không bao giờ nằm trong vùng chụp** (tránh OCR chính bản dịch). Windows thêm `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`. Android: nếu buộc phải chồng thì cắt vùng chụp tránh phần overlay.
- Overlay chung: nền tối bán trong suốt, chữ trắng, font hỗ trợ tiếng Việt (Windows: Segoe UI), cỡ chữ và độ trong cấu hình được, tùy chọn hiện bản gốc song song.
- Windows một lần: `Ctrl+Alt+T` chọn vùng → overlay (Esc / click ngoài để đóng, nút copy, nút sửa). `Ctrl+Alt+L` bật/tắt Live. Tray: bật/tắt Live, đổi engine OCR/dịch, mở cài đặt, thoát.
- Android: nút nổi — chạm mở menu: **Dịch vùng Live** / **Toàn màn hình** / **Chọn vùng mới**; thông báo foreground service có nút dừng.
- **Toàn màn hình (một lần):** Windows `Ctrl+Alt+F`; Android: menu nút nổi → "Toàn màn hình". Chụp cả màn hình → OCR → nhóm **khối chữ** theo vị trí → lọc khối chỉ số/ký hiệu → cache → dịch batch → overlay **đè đúng vị trí từng khối**; hiện "Đang dịch…", khối nào xong hiện trước. Esc / chạm ra ngoài để đóng. Chạm một khối: bản gốc, copy, sửa, **"Dùng khối này làm vùng Live"** (lưu vào hồ sơ game). **Không có Live toàn màn hình.**
- Xử lý đúng DPI scaling (125%, 150%) và nhiều màn hình trên Windows.

## 12. Cache, dữ liệu, model

- Cache LRU (key = câu đã chuẩn hóa + model id) + SQLite giữ giữa các lần chạy.
- Ghi `translations.jsonl` (gốc, dịch, model, game) và `corrections.jsonl` — có thể tắt trong cấu hình.
- Model đăng trên **repo model public ở Hugging Face Hub** (repo code private nên không dùng Release để chứa model), kèm `manifest.json` (tên, nền tảng, định dạng, URL, SHA-256, kích thước, phiên bản). App đọc manifest từ URL cố định, **chỉ tải model người dùng chọn**, kiểm SHA-256, lưu vào thư mục dữ liệu app; xóa/đổi model trong cài đặt. Kiểm tra giấy phép từng model trước khi đăng lại.
- Dung lượng đo ở Phase 0: CT2 opus-mt 78 MB, CT2 vinai 439 MB, ONNX opus-mt (Android) 131 MB. App Windows ước tính ~250–350 MB, `.apk` ước tính ~40–60 MB (chưa gồm model).
- ONNX Android: nén int8 **per-channel**, nén encoder + 2 decoder **trước** rồi mới merge. `onnxruntime` Python và `ortVersion` Gradle **phải cùng phiên bản** (hiện 1.32.0).

`windows/config.yaml` mẫu:

```yaml
hotkeys:
  translate_region: "ctrl+alt+t"
  translate_fullscreen: "ctrl+alt+f"
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
  active_interval_ms: 100
  settle_ms: 250
  max_wait_ms: 2000
  area_min_interval_ms: 1000   # Live vùng lớn: tối đa 1 OCR mỗi giây
  area_max_blocks: 30
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
| Toàn màn hình: OCR cả màn hình | < 500 ms | < 500 ms |
| Toàn màn hình: khối đầu tiên hiện / tất cả (~20 khối) | < 1 s / < 5 s | < 1 s / < 3 s |
| CPU khi Live và màn hình không đổi | < 2% | không OCR/dịch |
| Live vùng lớn khi màn hình đổi liên tục | ≤ 1 OCR/giây | ≤ 1 OCR/giây |
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

### Phase 0 — Khởi tạo & spike ✅ (kết quả: [docs/superpowers/reports/2026-11-17-phase0-results.md](docs/superpowers/reports/2026-11-17-phase0-results.md))
- [x] Cấu trúc monorepo, `.gitignore`, `ci.yml` khung chạy được.
- [x] Spike A (đo trên 6 ảnh Reverse: 1999: Windows OCR CER 2,4% / 27 ms, chốt mặc định; RapidOCR ~5 s): `winocr` trên ảnh chụp thoại Reverse: 1999 (và thử RapidOCR) — đo độ chính xác, tốc độ. Thiếu gói English OCR thì in hướng dẫn cài.
- [x] Spike B: vinai + opus-mt qua CT2 int8, so với `transformers` gốc (đặc biệt token ngôn ngữ mBART).
- [x] Spike C (đạt: 53 ms/câu, +177 MB RAM): opus-mt ONNX int8 (encoder + decoder merged có KV-cache, export bằng `optimum`) + SentencePiece + vòng giải mã greedy bằng Kotlin, ORT CPU 2 luồng (thử thêm XNNPACK EP), trong app thử tối thiểu. **Đạt** nếu trên POCO X8 Pro: < ~300 ms/câu ~20 từ, RAM < 400 MB, output khớp bản Python. **Không đạt** → phương án dự phòng: ML Kit Translation (en→vi offline, ~30 MB; chất lượng trung bình, không fine-tune được).

### Phase 1 — Lõi Windows (CLI) ✅ (plan: [docs/superpowers/plans/2026-11-17-phase1-windows-core.md](docs/superpowers/plans/2026-11-17-phase1-windows-core.md))
- [x] `capture`, `ocr/windows_ocr`, `text/postprocess`, `glossary`, `translate/ct2`, `cache`, `models`, `pipeline`.
- [x] `python -m app.cli --image sample.png` / `--screen x,y,w,h` in bản dịch.
- [x] Fixtures dùng chung (`shared/fixtures/postprocess/`, quy tắc trong README) + unit test. `windows/scripts/benchmark.py`.
- [x] `models.yml` (chạy tay) — **còn chờ người dùng** tạo repo HF + secret `HF_TOKEN` và chạy lần đầu.
- Placeholder thuật ngữ: **`[i]`** (vinai giữ 10/10; `⟦i⟧` bị xóa 0/10).
- Benchmark (laptop, cache tắt, trung vị 3 lần; OCR 20–60 ms):

| Model / beam | 1 câu thoại | 2 câu thoại | Load (gồm import transformers) |
|---|---|---|---|
| vinai / 2 | 270–310 ms | **780–950 ms** (vượt ngân sách Live 400 ms) | ~8,5 s |
| vinai / 1 | 290–305 ms | 620–810 ms | ~9 s |
| opus-mt / 2 | 65–105 ms | 205–280 ms | ~8 s |

  → Phase 3 (Live): hiện **từng câu ngay khi dịch xong** (câu đầu ~300 ms) thay vì đợi cả đoạn; cân nhắc lại vinai vs opus cho Live sau khi người dùng thử.

> **Thứ tự (người dùng chọn 2026-11-18, phương án C):** mỗi nền tảng có bản dùng được sớm (Phase 2 Windows, Phase 3 Android, đều chế độ một lần + toàn màn hình), rồi làm **Live một lần cho cả hai** ở Phase 4 (logic chờ ổn định / vùng lớn dùng chung qua fixtures).

### Phase 2 — GUI Windows (một lần + toàn màn hình)
- [ ] Tray + phím tắt toàn cục; `selector` (DPI, đa màn hình); `overlay` (copy, Esc, sửa).
- [ ] Chế độ **toàn màn hình** (`Ctrl+Alt+F`): nhóm khối chữ, lọc, overlay đè từng khối, "Dùng khối này làm vùng Live" (lưu vùng, dùng ở Phase 4).
- [ ] Model load trong worker thread (một `Pipeline` duy nhất cho thread đó), UI không đơ; "Đang tải model…", "Đang dịch…".
- [ ] `build-windows.yml`, phát hành bản Windows đầu tiên.

### Phase 3 — App Android cơ bản (một lần + toàn màn hình)
- [ ] MediaProjection foreground service, overlay + nút nổi (menu: **Dịch vùng** / **Toàn màn hình** / **Chọn vùng mới**), ML Kit OCR, ONNX dịch (`mt-core`), postprocess Kotlin (pass `shared/fixtures/postprocess`), thuật ngữ, cache.
- [ ] Model: đóng gói trong APK (hoặc tải theo manifest). Đo ngân sách trên POCO X8 Pro.
- [ ] `build-android.yml`, thêm `.apk` vào Release.

### Phase 4 — Live + hồ sơ game (Windows + Android)

> Chia hai kế hoạch: **4a — Live** ([plan](docs/superpowers/plans/2026-11-18-phase4a-live.md)): máy trạng thái + Live thoại + Live vùng lớn trên cả hai nền tảng; **4b** ([plan](docs/superpowers/plans/2026-11-18-phase4b-profiles.md)): **Live đè lên chữ gốc (toàn màn hình / vùng) + realtime từng câu**, hồ sơ game, sửa bản dịch, release `v0.1.0`.

- [x] `live` với phát hiện thay đổi + chờ ổn định + overlay click-through; **hiện từng câu ngay khi dịch xong** (vinai 2 câu ~0,9 s). Windows: `Ctrl+Alt+L`, CPU Live nhàn rỗi đo 0,15% (60 s, vùng 900×200). Android: menu nút nổi "Bật Live". *(4a — chờ người dùng nghiệm thu trên game thật.)*
- [x] **Live vùng lớn** (`live.mode: area`): giới hạn 1 OCR/s, so khối mới/cũ, chỉ dịch khối mới, overlay đè từng khối. Chế độ chọn trong tray / menu, nhớ giữa các lần chạy (hồ sơ theo game ở 4b).
- [ ] `profiles` tự nhận game; tách tên / lựa chọn; sửa bản dịch → `overrides` + `corrections.jsonl`; xem lại khóa cache (thuật ngữ / phiên bản model).
- [ ] Fixtures chuỗi khung hình dùng chung cho máy trạng thái Live (Python ↔ Kotlin). Đo FPS trước/sau. Release `v0.1.0`.

### Phase 5 — Hoàn thiện
- [ ] Màn hình cài đặt (cả hai nền tảng); xem/sửa bảng thuật ngữ; tải/cập nhật/xóa model.
- [ ] Engine từ xa: `training/kaggle_serve.ipynb` + client `remote` có fallback về model local (Windows + Android). Test: server tắt / chậm / sai token → en vẫn dịch bằng local, ja báo lỗi rõ ràng.
- [ ] **Tiếng Nhật:** OCR tiếng Nhật (Windows OCR gói Japanese / RapidOCR japan; ML Kit Japanese), lọc furigana, hậu xử lý riêng (không khoảng trắng, tách câu theo 。！？), fixtures tiếng Nhật; dịch qua remote LLM.

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
