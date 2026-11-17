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
