# ScreenTrans

OCR màn hình và dịch **Anh → Việt** khi chơi game, chạy **ngay trên máy** (không cần mạng sau khi có model), cho **Windows** và **Android**.
Thiết kế: [docs/superpowers/specs/2026-11-16-screentrans-design.md](docs/superpowers/specs/2026-11-16-screentrans-design.md) · Đặc tả triển khai: [AGENT.md](AGENT.md).

## Tải về

Bản build mới nhất từ `main`: [Releases → nightly](https://github.com/ngocanh0202/ScreenTrans/releases/tag/nightly).

| Nền tảng | File | Ghi chú |
|---|---|---|
| Windows 10/11 | `ScreenTrans-windows.zip` | Giải nén, chạy `ScreenTrans.exe` (biểu tượng chữ **T** ở khay hệ thống). Lần đầu tự tải model vinai theo manifest (~440 MB). Cần gói **English OCR** của Windows. |
| Android 10+ | `ScreenTrans-android.apk` | Cài APK, mở app, cấp lần lượt: hiển thị trên ứng dụng khác → thông báo → ghi màn hình. Model opus-mt đã có sẵn trong APK. |

## Tính năng hiện có

| Tính năng | Dùng để | Windows | Android |
|---|---|---|---|
| Dịch vùng | Dịch chữ trong vùng đã chọn | `Ctrl+Alt+T` | Nút nổi → "Dịch vùng" |
| Toàn màn hình | Dịch mọi chữ trên màn hình một lần, bản dịch đè đúng chỗ | `Ctrl+Alt+F` | Nút nổi → "Toàn màn hình" |
| Live | Tự dịch khi chữ đổi, bản dịch đè lên chữ gốc, hiện từng câu ngay khi câu đó hiện xong | `Ctrl+Alt+L` | Nút nổi → "Bật Live" |
| Phạm vi Live | Toàn màn hình, hoặc chỉ các vùng đã chọn (kèm vùng bỏ qua) | Tray → "Live dịch", "Vùng Live" | Nút nổi → "Live dịch", "Chọn / sửa vùng (bỏ qua)" |
| Hồ sơ theo game | Tự nhận game, nhớ vùng, phạm vi Live, bản sửa riêng từng game | Tự động | Usage Access hoặc chọn tay ("Game ▸") |
| Sửa bản dịch | Lần sau gặp đúng câu sẽ dùng bản của bạn; thêm thuật ngữ | `Ctrl+Alt+E`, nút "Sửa" | "Sửa bản dịch gần nhất", nút "Sửa" |
| Bảng thuật ngữ | Giữ nguyên hoặc dịch cố định tên riêng, thuật ngữ | ✓ | ✓ |
| Đổi model | `vinai-en2vi` (mặc định) hoặc `opus-mt-en-vi` | Tray → "Model" | `opus-mt-en-vi` |
| Dịch bằng mô hình lớn qua mạng | Dịch tự nhiên hơn, có ngữ cảnh câu trước và người nói: Gemini, OpenAI, Claude hoặc server Kaggle riêng; lỗi / hết hạn mức thì tự dùng model trên máy | Cài đặt → "Dịch bằng" (theo game) | Sắp có |
| Chọn bộ OCR | Windows OCR (mặc định) hoặc RapidOCR | Cài đặt → "Bộ OCR" | ML Kit |

Dịch qua mạng: nhập key trong Cài đặt (lưu mã hóa bằng DPAPI, không ghi ra file cấu hình hay nhật ký). Chữ trong game được gửi tới nhà cung cấp đã chọn; có giới hạn ký tự mỗi ngày (mặc định 50 000). Server Kaggle miễn phí: chạy [training/kaggle_serve.ipynb](training/kaggle_serve.ipynb), dán URL + token vào Cài đặt.

Android: khi cấp quyền ghi màn hình, chọn **"Một ứng dụng" → game** để bản dịch Live không nháy.
Dữ liệu Windows ở `%LOCALAPPDATA%\ScreenTrans` (tray → "Mở thư mục dữ liệu"), cấu hình ở [windows/config.yaml](windows/config.yaml).

## Sắp làm

- **Phase 4b** ([plan](docs/superpowers/plans/2026-11-18-phase4b-profiles.md)): nghiệm thu trên game thật, đo FPS, release **v0.1.0** ([CHANGELOG](CHANGELOG.md)).
- **Phase 5:** màn hình cài đặt, dịch từ xa qua Kaggle, tiếng Nhật.
- **Phase 6:** fine-tune model.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `windows/` | App Windows (Python 3.11 + PySide6, đóng gói PyInstaller) |
| `android/` | App Android (Kotlin; module `text-core`, `mt-core`, `app-core` test được trên JVM, `app`) |
| `shared/` | Schema, thuật ngữ, **fixtures dùng chung** (hậu xử lý, Live) — Python là chuẩn, Kotlin pass cùng bộ |
| `models/` | Script export/verify model (CTranslate2, ONNX), manifest |
| `spikes/` | Mã thử nghiệm Phase 0 |
| `training/` | Notebook Kaggle (fine-tune, server từ xa) |

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

### Dòng lệnh (Windows)

```powershell
# model: export một lần (cần models/requirements.txt + torch CPU), hoặc để app tải theo manifest
.venv\Scripts\python -m models.export ct2 vinai-en2vi
cd windows
..\.venv\Scripts\python -m app.cli --image ..\anh.png --model-dir ..\models\out\vinai-en2vi-ct2 `
    --glossary ..\shared\glossary\games\reverse1999.json --show-source
..\.venv\Scripts\python -m app.cli --screen 520,750,1180,160 --model-dir ..\models\out\vinai-en2vi-ct2
```

Tùy chọn: `--json` (kết quả JSON), `--timings` (thời gian từng bước ra stderr), `--config` (mặc định `windows/config.yaml`).
Mã thoát: 0 xong (kể cả không có chữ), 2 thiếu/không tải được model, 3 thiếu gói English OCR của Windows, 4 tham số sai.

Benchmark: `.venv\Scripts\python windows/scripts/benchmark.py --model-dir models/out/vinai-en2vi-ct2`

### CI/CD

- `ci`: test Python + test JVM Android trên mỗi lần push.
- `build-windows`, `build-android`: build exe / APK; trên `main` cập nhật release **`nightly`**.
- `release`: đẩy tag `v*` → release chính thức kèm exe zip + APK.
- `models`: (chạy tay) đăng model + manifest lên release `models-v1` để app Windows tự tải.

## Bản quyền

Mã nguồn: **AGPL-3.0** ([LICENSE](LICENSE)). Model và dữ liệu bên thứ ba có giấy phép riêng — xem [NOTICE.md](NOTICE.md) (opus-mt: Apache-2.0, vinai: AGPL-3.0, wordfreq: CC BY-SA 4.0).
