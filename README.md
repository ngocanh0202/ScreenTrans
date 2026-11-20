# ScreenTrans

OCR màn hình và dịch **Anh → Việt** khi chơi game, cho **Windows** và **Android**. Mặc định dịch **ngay trên máy**
(không cần mạng sau khi có model); tùy chọn dịch bằng mô hình ngôn ngữ lớn qua mạng (Gemini / OpenAI / Claude / Kaggle).
Thiết kế: [docs/superpowers/specs/2026-11-16-screentrans-design.md](docs/superpowers/specs/2026-11-16-screentrans-design.md) · Đặc tả triển khai: [AGENT.md](AGENT.md) · Thay đổi: [CHANGELOG.md](CHANGELOG.md).

## Tải về

Bản build mới nhất từ `main`: [Releases → nightly](https://github.com/ngocanh0202/ScreenTrans/releases/tag/nightly).

| Nền tảng | File | Ghi chú |
|---|---|---|
| Windows 10/11 | `ScreenTrans-windows.zip` | Giải nén, chạy `ScreenTrans.exe` (biểu tượng chữ **T** ở khay hệ thống). Model tải từ Hugging Face ([`anhbui02/screentrans-models`](https://huggingface.co/anhbui02/screentrans-models)) lần đầu dùng. Cần gói **English OCR** của Windows. |
| Android 10+ | `ScreenTrans-android.apk` | Cài APK, mở app, cấp lần lượt: hiển thị trên ứng dụng khác → thông báo → ghi màn hình, rồi **▶ Bắt đầu**. Model opus-mt có sẵn trong APK. |

Android: khi cấp quyền ghi màn hình, chọn **"Một ứng dụng" → game** để bản dịch Live không nháy.

## Tính năng

| Tính năng | Dùng để | Windows | Android |
|---|---|---|---|
| Dịch vùng | Dịch chữ trong vùng đã chọn | `Ctrl+Alt+T` | Nút nổi → "Dịch 1 lần" + "Vùng" |
| Toàn màn hình | Dịch mọi chữ trên màn hình một lần, bản dịch đè đúng chỗ | `Ctrl+Alt+F` | Nút nổi → "Toàn màn hình" |
| Live | Tự dịch khi chữ đổi, bản dịch đè lên chữ gốc từng câu ngay khi câu hiện xong; câu đã dịch không gửi dịch lại; khung không nhảy, không đè nhau, câu ngắn không rớt chữ | `Ctrl+Alt+L` | Nút nổi → "Tự động" |
| Kiểu bản dịch | "Giống game" (cỡ chữ + màu lấy từ game, màu giữ nguyên trong cả hộp thoại) hoặc "Dễ đọc" (chữ trắng nền tối); cỡ chữ; bản dịch dài → kéo dài khung hoặc thu nhỏ chữ | Cài đặt | ⚙ Cài đặt, hoặc màn hình mở app |
| Phạm vi Live | Toàn màn hình, hoặc chỉ các vùng đã chọn (kèm vùng bỏ qua); chữ nghiêng được vẽ nghiêng theo | Tray → "Live dịch", "Vùng Live" | Nút nổi → "Vùng" / "Toàn màn hình", "Chọn vùng", ⚙ → "Vùng bỏ qua" |
| Hồ sơ theo game | Tự nhận game; nhớ vùng, kiểu, bộ dịch, bản sửa, thuật ngữ riêng từng game | Tự động | Usage Access hoặc chọn tay (⚙ → "🎮 Game") |
| Sửa bản dịch | Lần sau gặp đúng câu sẽ dùng bản của bạn; chọn chữ ở câu gốc để thêm thuật ngữ (giữ nguyên / dịch cố định), có gợi ý tên riêng | `Ctrl+Alt+E` | Nút nổi → "✍ Sửa bản dịch" |
| Bảng thuật ngữ | Xem / thêm / sửa / xóa thuật ngữ của game (để trống bản dịch = giữ nguyên); áp dụng ngay | Cài đặt → "Xem / sửa thuật ngữ…", tray → "Thuật ngữ của game…" | ⚙ → "📖 Thuật ngữ" |
| Quản lý model | Danh sách model trên Hugging Face và trên máy: tải về (kiểm tra SHA-256), cập nhật, xóa, dùng; thêm model tự export từ thư mục (Windows) | Cài đặt → "Quản lý model…", tray → "Model" | ⚙ → "🧠 Model", hoặc "🌐 Dịch bằng" → Máy |
| Model trên máy | `vinai-en2vi` (chất lượng), `opus-mt-en-vi` (nhanh), `screentrans-en-vi` (opus-mt tinh chỉnh cho thoại game, Phase 6) | Cả ba | opus-mt (có sẵn) + model tải về |
| Dịch bằng mô hình lớn qua mạng | Dịch tự nhiên hơn: nhớ 10 câu trước của từng game, người nói, ghi chú game (nhân vật, xưng hô) và các câu bạn đã sửa; model riêng cho Live; lỗi / hết hạn mức → tự dùng model trên máy | Cài đặt → "Dịch bằng" (theo game) | ⚙ → "🌐 Dịch bằng" (theo game) |
| Bộ OCR | Windows OCR (mặc định) hoặc RapidOCR | Cài đặt → "Bộ OCR" | ML Kit |
| Tắt nhanh | Dừng ScreenTrans | Tray → "Thoát" | Nút nổi → "✖ Tắt", hoặc "■ Dừng" ở màn hình mở app |

Dịch qua mạng: nhập key trong Cài đặt (Windows: mã hóa DPAPI; Android: Android Keystore; không ghi ra file cấu hình
hay nhật ký). Chữ trong game được gửi tới nhà cung cấp đã chọn; có giới hạn ký tự mỗi ngày (mặc định 50 000).
Server Kaggle miễn phí: chạy [training/kaggle_serve.ipynb](training/kaggle_serve.ipynb), dán URL + token vào Cài đặt.

Dữ liệu Windows ở `%LOCALAPPDATA%\ScreenTrans` (tray → "Mở thư mục dữ liệu"), cấu hình ở [windows/config.yaml](windows/config.yaml).

## Model dịch riêng (Phase 6)

`screentrans-en-vi` = `opus-mt-en-vi` tinh chỉnh trên Kaggle bằng **dữ liệu giấy phép mở** (ALT, Tatoeba, translatewiki,
ELRC, NLLB, ParaCrawl-Bonus — [báo cáo giấy phép](docs/superpowers/reports/2026-11-20-en-vi-licenses.md)). Notebook
[training/kaggle_finetune.ipynb](training/kaggle_finetune.ipynb) huấn luyện, chấm điểm so với model gốc, và (có secret
`HF_TOKEN`, điểm cao hơn model gốc) **tự export + đăng lên** `anhbui02/screentrans-models` → app hiện "Có bản mới".
Dữ liệu sinh bằng LLM (`training/distill_data.py`, key của bạn) chỉ để dùng riêng, không phát hành.
Hướng dẫn: [training/README.md](training/README.md).

## Sắp làm

- Nghiệm thu trên game thật, đo FPS, release **v0.1.0**.
- Phase 5: chọn beam / số luồng mặc định theo kết quả `windows/scripts/bench_models.py`; đo tốc độ trên Android.
- Phase 6: chạy notebook trên Kaggle, đánh giá model `screentrans-en-vi`.
- Phase 7: tiếng Nhật (OCR, lọc furigana, dịch qua LLM).

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `windows/` | App Windows (Python 3.11 + PySide6, đóng gói PyInstaller) |
| `android/` | App Android (Kotlin; module `text-core`, `mt-core`, `app-core` test được trên JVM, `app`) |
| `shared/` | Schema, thuật ngữ, **fixtures dùng chung** (hậu xử lý, Live, bố cục, thuật ngữ, danh sách model, câu lệnh LLM) — Python là chuẩn, Kotlin pass cùng bộ |
| `models/` | Export / verify model (CTranslate2, ONNX), manifest và đăng lên Hugging Face |
| `training/` | Fine-tune (dữ liệu mở, notebook Kaggle), dữ liệu riêng từ LLM, server dịch Kaggle |
| `spikes/` | Mã thử nghiệm (Phase 0, OpenCV) |

## Phát triển

```powershell
uv python install 3.11
uv venv --python 3.11 .venv
uv pip install --python .venv -r windows/requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

- Chạy app Windows từ mã nguồn: `cd windows; ..\.venv\Scripts\python -m app` (thêm `--config <file>` nếu cần).
- Android: build trên CI (`build-android`); test JVM chạy được trên máy có JDK 17: `cd android; ./gradlew :text-core:test :app-core:test`.
- Bộ OCR RapidOCR (tùy chọn, chậm, ~190 MB, không có trong exe): `uv pip install --python .venv -r windows/requirements-rapidocr.txt`, rồi chọn trong Cài đặt → Bộ OCR.
- Export model (máy dev): cài thêm torch CPU rồi `uv pip install --python .venv -r models/requirements.txt`.

### Model: export và đăng lên Hugging Face

```powershell
.venv\Scripts\python -m models.export ct2  vinai-en2vi                 # Windows (CTranslate2 int8)
.venv\Scripts\python -m models.export onnx opus-mt-en-vi               # Android (ONNX int8)
.venv\Scripts\python -m models.export ct2  screentrans-en-vi --hf-id D:\path\screentrans-en-vi   # model đã fine-tune
# đăng (không có --yes: chỉ in ra sẽ tải gì; token ghi trong HF_TOKEN); --only để đăng một model, giữ các model khác
.venv\Scripts\python -m models.manifest --version 1 --stage models\out\hf `
    --merge-from https://huggingface.co/anhbui02/screentrans-models/resolve/main/manifest.json `
    --upload anhbui02/screentrans-models --yes
```

### Đo model, so sánh bộ dịch

- `.venv\Scripts\python windows/scripts/bench_models.py` — tốc độ beam 1/2/4 × luồng 1/2/4 và bản dịch từng beam → `windows/out/bench_models.html`.
- `.venv\Scripts\python windows/scripts/compare_engines.py` — vinai / opus-mt / LLM cạnh nhau trên câu thoại đã ghi.

### Dòng lệnh (Windows)

```powershell
cd windows
..\.venv\Scripts\python -m app.cli --image ..\anh.png --model-dir ..\models\out\vinai-en2vi-ct2 `
    --glossary ..\shared\glossary\games\reverse1999.json --show-source
..\.venv\Scripts\python -m app.cli --screen 520,750,1180,160 --model-dir ..\models\out\vinai-en2vi-ct2
```

Tùy chọn: `--json` (kết quả JSON), `--timings` (thời gian từng bước ra stderr), `--config` (mặc định `windows/config.yaml`).
Mã thoát: 0 xong (kể cả không có chữ), 2 thiếu/không tải được model, 3 thiếu gói English OCR của Windows, 4 tham số sai.

### CI/CD

- `ci`: test Python + test JVM Android trên mỗi lần push.
- `build-windows`, `build-android`: build exe / APK (trên `main` và nhánh `phase-*`); trên `main` cập nhật release **`nightly`**.
- `release`: đẩy tag `v*` → release chính thức kèm exe zip + APK.
- `models`: (chạy tay) export và đăng model lên GitHub release `models-v1` (cũ; app giờ đọc manifest trên Hugging Face — đăng bằng `models.manifest --upload` ở trên).

## Bản quyền

Mã nguồn: **AGPL-3.0** ([LICENSE](LICENSE)). Model và dữ liệu bên thứ ba có giấy phép riêng — xem [NOTICE.md](NOTICE.md)
(opus-mt: Apache-2.0 / CC-BY 4.0, vinai: AGPL-3.0, wordfreq: CC BY-SA 4.0; dữ liệu huấn luyện: `DATA_LICENSES.md` đi kèm model).
