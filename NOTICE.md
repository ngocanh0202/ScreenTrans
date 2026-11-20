# Bản quyền & nguồn bên thứ ba

Mã nguồn ScreenTrans: **GNU AGPL-3.0** (xem [LICENSE](LICENSE)).

## Model dịch (không nằm trong repo — export/tải riêng)

| Model | Nguồn | Giấy phép | Ghi chú |
|---|---|---|---|
| `Helsinki-NLP/opus-mt-en-vi` | Helsinki-NLP / OPUS-MT (Tiedemann & Thottingal, 2020), Hugging Face | Apache-2.0 (thẻ HF); OPUS-MT ghi CC-BY 4.0 cho model phát hành | Cả hai đều cho phép phân phối lại / thương mại, **ghi công** Helsinki-NLP / OPUS-MT |
| `vinai/vinai-translate-en2vi-v2` | VinAI Research, Hugging Face | AGPL-3.0 | Phân phối app kèm model này → công bố mã nguồn theo AGPL (repo này AGPL-3.0). VinAI đề nghị trích dẫn bài báo INTERSPEECH 2022 khi dùng trong phần mềm khác |

Model fine-tune (Phase 6) mang theo giới hạn của dữ liệu huấn luyện: model phát hành chỉ dùng dữ liệu giấy phép mở
(xem [báo cáo rà giấy phép](docs/superpowers/reports/2026-11-20-en-vi-licenses.md)); không dùng PhoMT / TED / QED (chỉ
nghiên cứu, phi thương mại) hay dữ liệu sinh bởi LLM thương mại.

## Dữ liệu

- `shared/glossary/common_words_en.txt`: 5.000 từ tiếng Anh thông dụng nhất, sinh từ [wordfreq](https://github.com/rspeer/wordfreq) (Robyn Speer) bằng `shared/glossary/make_common_words.py`. Dữ liệu wordfreq: **CC BY-SA 4.0** — file này phân phối lại theo cùng giấy phép.
- Fixtures và câu thử nghiệm trong repo là **câu tự viết**; toạ độ OCR lấy từ ảnh chụp màn hình của người dùng (ảnh không nằm trong repo). Tên nhân vật trong `shared/glossary/games/` chỉ dùng làm thuật ngữ.

## Thư viện chính

CTranslate2 (MIT), ONNX Runtime (MIT), transformers / tokenizers (Apache-2.0), sentencepiece (Apache-2.0), PySide6 (LGPL-3.0), mss (MIT), winocr (MIT), Pillow (MIT-CMU), PyYAML (MIT), Gson (Apache-2.0).

Windows OCR (Windows.Media.Ocr) và ML Kit là thành phần của hệ điều hành / SDK, dùng theo điều khoản của nhà cung cấp.
