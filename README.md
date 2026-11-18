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

| Tính năng | Windows | Android |
|---|---|---|
| **Dịch một vùng** — kéo chọn vùng, bản dịch hiện cạnh vùng (nút Copy) | `Ctrl+Alt+T` | Nút nổi → "Dịch vùng" |
| **Nhiều vùng** — dịch nhiều vùng cùng lúc, kéo để dời / đổi kích thước | — | Nút nổi → "Chọn / sửa vùng" |
| **Toàn màn hình (một lần)** — bản dịch đè đúng chỗ từng khối chữ, khối nào xong hiện trước; chạm/bấm một khối để xem bản gốc | `Ctrl+Alt+F` | Nút nổi → "Toàn màn hình" |
| **Live — Khung thoại** — tự dịch mỗi khi chữ trong vùng đổi, **chờ chữ chạy xong** rồi mới dịch, hiện **từng câu**; bản dịch đặt ngoài vùng, không che chữ gốc | `Ctrl+Alt+L` | Nút nổi → "Bật Live" |
| **Live — Vùng lớn** — cho game thoại bong bóng: bản dịch đè lên từng bong bóng, chỉ dịch bong bóng mới, tối đa 1 lần OCR/giây | Tray → "Chế độ Live" | Nút nổi → "Live: Vùng lớn" |
| Overlay Live không chặn chuột / chạm vào game | ✓ | ✓ |
| Overlay không lọt vào ảnh chụp (không OCR chính bản dịch) | ✓ (loại khỏi ảnh chụp) | ✓ (đặt ngoài vùng / ẩn khi chụp) |
| Đổi model dịch | Tray → "Model": `vinai-en2vi` (mặc định, chất lượng cao) / `opus-mt-en-vi` | `opus-mt-en-vi` |

**Live chạy thế nào:** chọn vùng **một lần** (Windows: lần đầu bấm `Ctrl+Alt+L` sẽ mở chọn vùng, đổi bằng tray → "Chọn lại vùng Live";
Android: dùng các vùng đã lưu). App so ảnh thu nhỏ của vùng theo nhịp 300 ms; chữ đổi → chụp nhanh hơn (100 ms) và chờ chữ đứng yên
250 ms mới OCR (nền động liên tục: tối đa 2 s). Màn hình đứng yên → không OCR (Windows đo CPU ~0,15%). Câu đã dịch được lấy từ cache.
Bật Live là dịch luôn câu đang hiện trong vùng.

**Xử lý văn bản:**
- Ghép dòng thành đoạn, tách câu, nhận dòng **tên nhân vật** (giữ nguyên, không dịch), sửa lỗi OCR hay gặp (`Ill` → `III`…), bỏ khối chỉ có số / ký hiệu.
- **Bảng thuật ngữ**: bảng chung + bảng riêng từng game (`shared/glossary/games/*.json`), `keep` (giữ nguyên) hoặc `map` (dịch cố định).
- **Tên riêng tự động**: từ viết hoa lặp lại ≥ 3 lần trong phiên, không phải từ tiếng Anh thông dụng → tự giữ nguyên.
- Game chặn chụp màn hình (FLAG_SECURE, Android) → báo rõ thay vì hiện kết quả rỗng.

**Dữ liệu (Windows `%LOCALAPPDATA%\ScreenTrans`):** model đã tải, `cache.sqlite` (cache bản dịch giữ giữa các lần chạy),
`translations.jsonl` (cặp gốc–dịch, tắt bằng `logging.save_pairs`), vùng và chế độ Live. Tray → "Mở thư mục dữ liệu".
Cấu hình: [windows/config.yaml](windows/config.yaml) (phím tắt, cỡ chữ / độ trong overlay, hiện bản gốc, tham số Live).

## Sắp làm

- **Phase 4b** ([plan](docs/superpowers/plans/2026-11-18-phase4b-profiles.md)): hồ sơ theo game (tự nhận game; vùng tên / thoại / lựa chọn; vùng bỏ qua; thuật ngữ và tham số riêng), **sửa bản dịch** trên overlay (lần sau dùng luôn, ghi `corrections.jsonl`), Live nhiều vùng trên Windows, đo FPS, release **v0.1.0**.
- **Phase 5:** màn hình cài đặt, engine dịch từ xa trên Kaggle (tùy chọn), **tiếng Nhật**.
- **Phase 6:** fine-tune model bằng dữ liệu đã sửa.

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
