# ScreenTrans

OCR màn hình và dịch Anh → Việt khi chơi game, chạy trên máy (Windows + Android). Thiết kế: [docs/superpowers/specs/2026-11-16-screentrans-design.md](docs/superpowers/specs/2026-11-16-screentrans-design.md) · Đặc tả triển khai: [AGENT.md](AGENT.md).

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `windows/` | App Windows (Python 3.11 + PySide6) |
| `android/` | App Android (Kotlin, Gradle) |
| `shared/` | Schema, thuật ngữ chung, fixtures test dùng chung |
| `models/` | Script export/verify model (CTranslate2, ONNX) |
| `spikes/` | Mã thử nghiệm Phase 0 |
| `training/` | Notebook Kaggle (fine-tune, server từ xa) |

## Môi trường Python

```powershell
uv python install 3.11
uv venv --python 3.11 .venv
uv pip install --python .venv -r windows/requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Export model (máy dev): cài thêm torch CPU rồi `uv pip install --python .venv -r models/requirements.txt`.

## Dùng thử (Phase 1 — dòng lệnh)

```powershell
uv pip install --python .venv -r windows/requirements-dev.txt
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

## Dùng app

**Windows (tray):** `Ctrl+Alt+T` dịch một vùng · `Ctrl+Alt+F` dịch toàn màn hình · `Ctrl+Alt+L` bật/tắt **Live**.
Lần đầu bật Live sẽ mở chọn vùng (kéo quanh khung thoại); đổi vùng bằng tray → "Chọn lại vùng Live".
Tray → "Chế độ Live": **Khung thoại** (bản dịch hiện ngay trên vùng, từng câu) hoặc **Vùng lớn** (game thoại
bong bóng: bản dịch đè lên từng khối chữ, chỉ dịch khối mới, tối đa 1 lần OCR/giây). Overlay Live không chặn chuột.

**Android (nút nổi T):** Dịch vùng / Toàn màn hình / Chọn / sửa vùng / **Bật Live** (dùng các vùng đã lưu) /
"Live: Khung thoại ↔ Vùng lớn". Thẻ bản dịch Live nằm ngoài vùng và không chặn chạm.

## Bản quyền

Mã nguồn: **AGPL-3.0** ([LICENSE](LICENSE)). Model và dữ liệu bên thứ ba có giấy phép riêng — xem [NOTICE.md](NOTICE.md) (opus-mt: Apache-2.0, vinai: AGPL-3.0, wordfreq: CC BY-SA 4.0).
