# ScreenTrans — Thiết kế

Ngày: 2026-11-16 · Trạng thái: chờ duyệt

## 1. Mục đích & lý do

Người dùng muốn **vừa chơi game vừa đọc bản dịch tiếng Việt** của chữ tiếng Anh trên màn hình, với độ trễ thấp, trên **laptop Windows** và **điện thoại Android**. Game điển hình: Reverse: 1999 (thoại kiểu visual novel, khung thoại cố định phía dưới, có câu lựa chọn), nhưng app phải dùng được cho **nhiều game khác nhau** mà không cần cấu hình nặng cho từng game.

Thiết bị:
- Laptop: GTX 1650 Ti 4 GB VRAM, 16 GB RAM.
- Điện thoại: POCO X8 Pro (dòng chip Dimensity tầm cao, RAM 8–12 GB — cần xác nhận khi benchmark).

## 2. Mục tiêu / Không làm / Thất bại nếu

**Mục tiêu**
- Dịch Anh → Việt chạy **hoàn toàn trên thiết bị** (offline), cả Windows lẫn Android.
- Hai cách dùng: **Live** (theo dõi vùng cố định, tự dịch khi chữ đổi) và **phím tắt / nút nổi** (chọn vùng bất kỳ, dịch một lần).
- **Hồ sơ theo game**, tự nhận game đang chạy.
- **Bảng thuật ngữ** chung + theo game, tự lớn dần từ các lần người dùng sửa.
- **CI/CD** (GitHub Actions) build `.exe` Windows và `.apk` Android.

**Không làm (bây giờ)**
- Ngôn ngữ nguồn khác tiếng Anh (thiết kế để thêm sau: mỗi model = một cặp ngôn ngữ → Việt).
- iOS, macOS, Linux.
- Fine-tune model trước khi có dữ liệu lỗi thật.
- Đăng nhập, cloud, đồng bộ giữa thiết bị.

**Thất bại nếu (dù chạy đúng)**
- Game bị giật / tụt FPS rõ rệt khi app chạy.
- Phải có mạng mới dịch được.
- Với game mới phải cấu hình nhiều mới dùng được.
- Bản dịch hiện chậm đến mức câu thoại đã qua.

## 3. Ràng buộc

- **Không dùng GPU cho OCR/dịch** trên laptop — 4 GB VRAM dành cho game. Dịch chạy CPU, int8, giới hạn số luồng.
- Không gọi API dịch online.
- Chụp màn hình Android phải qua MediaProjection (người dùng cấp quyền mỗi phiên); overlay cần quyền `SYSTEM_ALERT_WINDOW`.
- File cài đặt không chứa model (model tải riêng lúc chạy lần đầu).
- **Chỉ dùng cá nhân** trên laptop và điện thoại của người dùng (*lựa chọn của Claude*). Không cần ký code Windows; SmartScreen cảnh báo `.exe` chưa ký là chấp nhận được.
- **Game chạy ở chế độ cửa sổ hoặc borderless** (*lựa chọn của Claude*). Fullscreen độc quyền (exclusive) **không hỗ trợ**: overlay thường không vẽ đè lên được, muốn làm phải hook DirectX, rủi ro bị anti-cheat. App hiện hướng dẫn đổi sang borderless khi phát hiện fullscreen.
- Android: minSdk 29 (Android 10), target SDK mới nhất (*lựa chọn của Claude*).

## 4. Các hướng đã cân nhắc

| Hướng | Mô tả | Đánh đổi | Kết luận |
|---|---|---|---|
| Kaggle + ngrok | Model chạy trên Kaggle, app gọi qua API public | Trễ mạng 300 ms+, phiên 12 h, URL ngrok đổi, vi phạm điều khoản Kaggle | **Loại.** Kaggle chỉ dùng để fine-tune. |
| A. Mỗi nền tảng tự dịch trên máy | Windows (Python) và Android (Kotlin) đều chạy model local | Phải làm phần suy luận 2 lần; điện thoại phải đủ mạnh | **Chọn.** Máy đủ mạnh, dùng mọi nơi, không phụ thuộc mạng. |
| B. Điện thoại nhờ laptop dịch qua Wi-Fi | Android chỉ OCR + overlay | Laptop phải bật, chỉ dùng ở nhà | Loại — POCO X8 Pro đủ mạnh để tự dịch. |
| C. B trước rồi lên A | | Làm hai lần đường đi | Loại cùng lý do trên. |

Người dùng chọn **A**.

## 5. Kiến trúc

Monorepo một GitHub repo (người dùng tự tạo):

```
screentrans/
├── windows/          # app Windows, Python 3.11 + PySide6
├── android/          # app Android, Kotlin
├── shared/           # schema JSON (hồ sơ game, bảng thuật ngữ), fixtures test dùng chung
├── models/           # script export/convert model (output không commit)
├── training/         # notebook Kaggle fine-tune (giai đoạn cuối)
└── .github/workflows/
```

Luồng xử lý giống nhau trên hai nền tảng:

```
Chụp vùng → (Live: phát hiện thay đổi + chờ chữ ổn định) → OCR → hậu xử lý (gộp dòng, tách tên/thoại, tách câu)
→ bảo vệ thuật ngữ (thay bằng placeholder) → cache → dịch batch → khôi phục thuật ngữ → overlay
```

### 5.1 OCR
- **Windows:** Windows OCR (`winocr`) mặc định; **RapidOCR** (model PaddleOCR chạy bằng onnxruntime) làm engine dự phòng cho font cách điệu / nền rối. *Lựa chọn của Claude:* RapidOCR thay vì PaddleOCR gốc vì nhẹ hơn nhiều khi đóng gói PyInstaller, cùng chất lượng model.
- **Android:** ML Kit Text Recognition (Latin, bản bundled — không cần Google Play Services tải về).
- Engine chọn theo hồ sơ game.

### 5.2 Dịch
- **Windows:** CTranslate2 int8, CPU, `inter_threads=1`, `intra_threads=2` (cấu hình được).
- **Android:** ONNX Runtime (encoder + decoder có KV-cache, export bằng `optimum`), int8, 2 luồng. Tokenizer SentencePiece chạy trên Android (qua onnxruntime-extensions hoặc thư viện SentencePiece JNI — chốt sau spike).
- **Model:** `vinai/vinai-translate-en2vi-v2` (chất lượng) và `Helsinki-NLP/opus-mt-en-vi` (nhanh). **Model mặc định mỗi nền tảng chốt bằng benchmark** theo ngân sách ở mục 7: dùng vinai nếu đạt, không thì opus-mt. *Dự kiến:* Windows = vinai, Android = opus-mt.
- Interface `Translator.translate(list[str]) -> list[str]` (dịch theo batch). Mỗi model ứng với **một cặp ngôn ngữ → Việt**; thêm ngôn ngữ = thêm model + OCR tương ứng.
- Model load một lần, chạy trên thread riêng; model chỉ chạy khi có chữ mới.

### 5.3 Hậu xử lý văn bản
- Sắp xếp dòng, nhóm đoạn theo khoảng cách dọc, nối dòng, sửa gạch nối cuối dòng, tách câu, bỏ dòng rác.
- **Tách tên nhân vật:** hồ sơ game có thể khai báo vùng `name` riêng; nếu không, heuristic: dòng đầu ngắn (≤ 3 từ, viết hoa chữ đầu, không có dấu câu cuối) nằm tách biệt phía trên → coi là tên, không dịch.
- **Câu lựa chọn:** mỗi lựa chọn (khối dòng tách biệt) dịch riêng, hiển thị đúng thứ tự.
- Logic này **viết một lần bằng Python** và có bộ test fixtures JSON trong `shared/` (input dòng OCR → output đoạn/câu kỳ vọng); bản Kotlin phải pass cùng bộ fixtures.

### 5.4 Bảng thuật ngữ
- Ba lớp: **chung** (HP, MP, Buff, Quest… — đi kèm app), **theo game**, **tự động** (tên riêng).
- Hai loại mục: `keep` (giữ nguyên, không dịch) và `map` (thay bằng bản dịch cố định).
- Cách áp dụng: trước khi dịch, thay thuật ngữ bằng placeholder (vd `⟦0⟧`); sau khi dịch, khôi phục. Nếu model làm hỏng placeholder → dịch lại câu đó không qua placeholder (fallback).
- **Tên riêng tự động:** từ viết hoa không đứng đầu câu, lặp ≥ 3 lần trong phiên, không có trong từ điển tiếng Anh thông dụng → đề xuất `keep` (tự áp dụng, người dùng xem/xóa được).
- **Sửa từ overlay** (*lựa chọn của Claude*), hai thao tác riêng:
  - **Sửa cả câu:** lưu vào `overrides` của hồ sơ game (key = câu nguồn đã chuẩn hóa → bản dịch người dùng). Câu đó lần sau luôn hiện bản sửa, không qua model. Đồng thời ghi vào `corrections.jsonl`.
  - **Đánh dấu từ/cụm từ:** chọn một từ trong câu gốc → `keep` hoặc nhập bản dịch cố định (`map`) → thêm vào bảng thuật ngữ của game.
- Thứ tự áp dụng: `overrides` → cache → thuật ngữ + model.

### 5.5 Hồ sơ game
- Một file JSON / game (schema trong `shared/`): định danh game (Windows: tên exe; Android: package name), các vùng (`dialogue`, `name`, `choices`, tùy chọn), engine OCR, thời gian chờ chữ ổn định, ngưỡng thay đổi, bảng thuật ngữ.
- **Tự nhận game:** Windows theo process cửa sổ foreground; Android theo `UsageStatsManager` (cần quyền Usage Access), không có quyền thì cho chọn tay.
- Game chưa có hồ sơ → tạo hồ sơ mặc định khi người dùng chọn vùng lần đầu.
- Tọa độ vùng lưu **tương đối theo cửa sổ game / màn hình** (tỉ lệ 0–1) để không lệch khi đổi độ phân giải hoặc DPI.

### 5.6 Chế độ Live
- Chụp vùng mỗi `interval_ms` (mặc định 300 ms).
- So ảnh thu nhỏ (grayscale 64 px chiều rộng, sai khác trung bình) với lần trước; dưới ngưỡng → bỏ qua (không OCR).
- **Chờ chữ ổn định:** khi phát hiện thay đổi, đợi đến khi ảnh không đổi trong `settle_ms` (mặc định 250 ms) rồi mới OCR — xử lý hiệu ứng chữ hiện dần.
- Text OCR giống lần trước → không dịch lại. Câu đã dịch → lấy từ cache.
- Overlay Live **click-through** (Windows: `WS_EX_TRANSPARENT`; Android: `FLAG_NOT_TOUCHABLE`), có nút nhỏ để tạm ẩn / chuyển sang chế độ tương tác (sửa bản dịch).
- **Vị trí: cạnh vùng thoại, không che chữ gốc** (mặc định phía trên khung thoại, như bản phác thảo đã thống nhất; không đủ chỗ thì đặt dưới). Overlay **không bao giờ nằm trong vùng chụp**, nếu không app sẽ OCR chính bản dịch của nó. Windows thêm `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` để chắc chắn. Android: nếu overlay buộc phải chồng lên vùng chụp (màn hình nhỏ) thì cắt vùng chụp tránh phần overlay.

### 5.7 Chế độ một lần
- Windows: phím tắt `Ctrl+Alt+T` → kéo chọn vùng → overlay bản dịch (Esc / click ngoài để đóng, nút copy, nút sửa). `Ctrl+Alt+L` bật/tắt Live.
- Android: nút nổi (bong bóng) → chạm để dịch vùng Live đã chọn, giữ để kéo chọn vùng mới.

### 5.8 Cache & dữ liệu
- LRU trong bộ nhớ + SQLite (giữ giữa các lần chạy), key = câu nguồn đã chuẩn hóa + model id.
- Ghi `translations.jsonl` (câu gốc, bản dịch, model, game) và `corrections.jsonl` — dữ liệu cho fine-tune sau này. Có thể tắt.

## 6. Phân phối model & CI/CD

- Model **không** nằm trong file cài đặt. Vì repo code là private (asset trong Release của repo private không tải được nếu không có token), **model được đăng lên một repo model public trên Hugging Face Hub** (*lựa chọn của Claude*), kèm `manifest.json` (tên, nền tảng, định dạng, URL, SHA-256, kích thước, phiên bản). App đọc manifest từ URL cố định, tải lần đầu, kiểm SHA-256, lưu vào thư mục dữ liệu app. Token ghi HF lưu trong GitHub Secrets (`HF_TOKEN`). Cần kiểm tra giấy phép từng model trước khi đăng lại (opus-mt: CC-BY 4.0; vinai: xem model card).
- Workflow GitHub Actions:
  - `ci.yml` (mỗi push/PR): pytest (Windows runner), unit test Android (`./gradlew test`), chạy fixtures dùng chung.
  - `build-windows.yml`: PyInstaller `--noconsole` trên `windows-latest` → artifact `.zip`.
  - `build-android.yml`: `./gradlew assembleRelease`, ký bằng keystore lưu trong GitHub Secrets → artifact `.apk`.
  - `release.yml` (khi push tag `v*`): chạy hai build trên và đính kèm vào GitHub Release.
  - `models.yml` (chạy tay `workflow_dispatch`): tải model HF, convert CT2 int8 + ONNX int8, verify, tạo manifest, upload lên repo model public trên HF Hub.
- Repo đề xuất private.

## 7. Ngân sách hiệu năng (tiêu chí nghiệm thu)

| Chỉ số | Windows | Android |
|---|---|---|
| Phím tắt: chọn vùng xong → hiện bản dịch (~50 từ) | < 500 ms | < 800 ms |
| Live: chữ ổn định → hiện bản dịch (1–2 câu) | < 400 ms | < 600 ms |
| CPU khi Live và màn hình không đổi | < 2% | không OCR/dịch |
| GPU dùng cho OCR/dịch | 0 | — |
| RAM thêm của app | < 1.5 GB | < 600 MB |
| FPS game | không giảm rõ rệt (đo trước/sau) | như Windows |

## 8. Thứ tự làm

0. **Khởi tạo + spike:** cấu trúc monorepo, CI khung. Spike: (a) winocr trên ảnh chụp Reverse: 1999; (b) vinai CT2 so với transformers gốc (token ngôn ngữ mBART); (c) opus-mt ONNX + tokenizer chạy trên Android, đo tốc độ.
1. **Lõi Windows (CLI):** capture, OCR, hậu xử lý, thuật ngữ, dịch, cache, benchmark → chốt model mặc định Windows.
2. **GUI Windows:** tray, phím tắt, chọn vùng (DPI, đa màn hình), overlay.
3. **Live + hồ sơ game + sửa bản dịch** trên Windows. Release Windows đầu tiên qua CI.
4. **App Android:** MediaProjection, ML Kit, ONNX, overlay, nút nổi, Live, hồ sơ, thuật ngữ. Release `.apk` qua CI.
5. **Hoàn thiện:** màn hình cài đặt, tải/cập nhật model, xem/sửa bảng thuật ngữ.
6. **Fine-tune trên Kaggle** (chỉ khi đã có đủ `corrections.jsonl`): train, đánh giá sacreBLEU/COMET, chỉ thay model nếu tốt hơn.

## 9. Để lại cho người triển khai

- Cách cụ thể tách encoder/decoder ONNX và vòng lặp giải mã (greedy/beam) trên Android.
- Thư viện tokenizer trên Android.
- Thư viện phím tắt toàn cục Windows (`keyboard` hoặc `pynput`).
- Chi tiết giao diện overlay và màn hình cài đặt (theo mô tả ở 5.6–5.7).
- Cấu trúc thư mục bên trong `windows/` và `android/`.
