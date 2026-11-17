# Phase 0 — Kết quả spike & quyết định

Ngày: 2026-11-17 · Nhánh: `phase-0` · Plan: [2026-11-16-phase0-init-and-spikes.md](../plans/2026-11-16-phase0-init-and-spikes.md)

## Tóm tắt

| Câu hỏi | Kết quả | Quyết định |
|---|---|---|
| A. OCR nào đọc tốt chữ game? | Đo trên 6 ảnh Reverse: 1999 thật: Windows OCR CER 2,4% / 27 ms (khung thoại); RapidOCR 7,1% / ~5 s. | **Windows OCR** mặc định (chốt). RapidOCR quá chậm — chỉ giữ làm tùy chọn, xem lại ở Phase 1. |
| B. CT2 có khớp `transformers` không, nhanh bao nhiêu? | Khớp (chrF 94,7 / 95,5). opus nhanh, vinai chậm 4–5× nhưng dịch tốt hơn rõ rệt. | Windows mặc định **opus-mt** theo tiêu chí spec; **vinai** tùy chọn. Xem "Cần người dùng quyết định". |
| C. opus-mt ONNX trên POCO X8 Pro? | 53 ms/câu, +177 MB RAM, load 1,4 s. | **ONNX opus-mt, CPU 2 luồng**. Không cần phương án ML Kit Translation. |

## A. OCR (Windows)

- `spikes/ocr/` — `cer()`, `prepare_image()`, `windows_ocr()`, `rapid_ocr()`, `python -m spikes.ocr.run`.
- Ảnh thử tổng hợp (chữ trắng nền đen, Segoe UI 40px): cả hai engine đọc đúng "Hello world".
- RapidOCR trả mỗi từ một khung → đã gộp theo dòng.
- Thiếu gói English OCR → `OcrEngineUnavailable` kèm hướng dẫn cài (test bằng monkeypatch).
- **Đo trên ảnh thật (2026-11-17):** 6 ảnh chụp màn hình điện thoại 2048×942 (qua Messenger, JPEG): 5 khung thoại (4 có tên "Druvis III", 1 lời dẫn) + 1 màn hình Log.

Khung thoại (cắt vùng tên + 2 dòng, `python -m spikes.ocr.run`):

| Engine | CER trung bình | ms trung vị |
|---|---|---|
| **Windows OCR** | **0,024** | **27** |
| RapidOCR | 0,071 | ~4.900 |

Toàn màn hình (`python -m spikes.ocr.fullscreen`, dòng "tìm thấy" khi CER ≤ 0,1):

| Ảnh | Windows: tìm thấy / ms | RapidOCR: tìm thấy / ms |
|---|---|---|
| 5 ảnh thoại (gồm AUTO/SKIP/EXIT) | 21/27 / 119–251 ms | 22/27 / 2.988–3.991 ms |
| Màn hình Log (10 dòng) | **9/10** / 122 ms | 4/10 / 5.833 ms |

- **Mọi câu thoại Windows OCR đọc đúng 100%.** Lỗi duy nhất lặp lại: tên **"Druvis III" → "Druvis Ill"** (số La Mã giống chữ "Ill" trong font serif). Không ảnh hưởng dịch (dòng tên không dịch); sửa bằng bảng thuật ngữ game hoặc quy tắc `Ill`→`III` cho dòng tên.
- Toàn màn hình: Windows OCR thỉnh thoảng bỏ sót / gộp nút "AUTO", "SKIP" — các nút này sẽ bị lọc anyway.
- RapidOCR chậm ~5 s/ảnh trên laptop (chưa tìm hiểu nguyên nhân) → không dùng được cho Live.
- **Còn thiếu:** ảnh có câu lựa chọn, menu/kho đồ, game có bong bóng thoại.

## B. Dịch trên Windows (CTranslate2 int8, laptop 14 luồng logic, máy rảnh)

| | opus-mt-en-vi | vinai-en2vi |
|---|---|---|
| chrF so với `transformers` fp32 (greedy) | 94,7 | 95,5 |
| Khớp tuyệt đối | 72% | 83% |
| Token ngôn ngữ (`vi_VN`) còn sót trong output, đếm trên token thô / output rỗng | — / không | 0/29 / không |
| Dung lượng | 78 MB | 439 MB |
| RAM thêm sau load | ~91 MB | ~454 MB |
| Thời gian load | 0,24 s | 1,5 s |
| Một câu (beam 2, 2 luồng) | ~70–85 ms | ~260–300 ms |
| Đoạn ~50 từ (beam 2, 2 luồng) | **~250 ms** | **~1.160–1.360 ms** |
| Đoạn ~50 từ (beam 1, 2 luồng) | ~220 ms | ~940 ms |
| 4 luồng | nhanh hơn chút (~165–200 ms) | không cải thiện đáng kể |

Chất lượng (trích):

| EN | opus-mt | vinai |
|---|---|---|
| Tap anywhere to continue. | Đang tiếp tục tìm kiếm bất cứ nơi nào. | Nhấn vào bất cứ đâu để tiếp tục. |
| Thanks for waiting! The server maintenance is complete. | Đã hoàn tất! | Cảm ơn bạn đã chờ đợi! Việc bảo trì máy chủ đã hoàn tất. |
| “Trust me,” she whispered. | “ Hãy tin tôi, nàng sẽ nói: “Hãy tin tôi! | “Tin tôi đi,” cô thì thầm. |
| Sonetto smiled. "I will follow you, Timekeeper." | Con trai tôi. "Tôi sẽ theo anh, Timekeeper." | Sonetto mỉm cười. "Tôi sẽ theo anh, Người chấm công." |
| Good morning, Timekeeper. | Chào buổi sáng, Time-Time. | Chào buổi sáng, Timekeeper. |

Nhận xét: vinai tốt hơn rõ ở câu UI, câu dài, tên riêng. opus làm hỏng nhiều câu UI ngắn. Cả hai đều sẽ hưởng lợi từ bảng thuật ngữ (giữ "Timekeeper", tên nhân vật).

## C. Android (ONNX Runtime 1.32.0, Xiaomi 2511FPC34G = POCO X8 Pro, Android 16, 8 lõi)

Model ONNX int8 per-channel: encoder 47 MB + decoder merged 81 MB (thư mục 131 MB). chrF so với `transformers` 90,8 (thấp hơn CT2 int8 một chút).

| Cấu hình | Load | ms/câu trung vị / p95 / max | Khớp golden | RAM (PSS) app |
|---|---|---|---|---|
| **CPU 2 luồng** | 1.370 ms | **53 / 73 / 109** | 19/20 | 276 MB (99 MB trước load → **+177 MB**) |
| CPU 4 luồng | 1.063 ms | 133 / 265 / 296 | 19/20 | 287 MB |
| XNNPACK 2 luồng | 969 ms | 55 / 70 / 116 | 19/20 | 274 MB |

- Tokenizer SentencePiece Kotlin thuần + vòng giải mã greedy: khớp **29/29** id với Python trên JVM (CI và máy dev).
- Trên điện thoại 19/20: một chỗ hòa điểm sát nút bị lật do kernel ARM — đúng dự đoán, không phải lỗi logic.
- 4 luồng chậm hơn 2 luồng (tranh lõi hiệu năng/tiết kiệm); XNNPACK không lợi gì với model int8 động.
- Bài học: phải nén int8 **per-channel** và **nén trước rồi mới merge decoder**; ORT Python và Java phải **cùng phiên bản** (1.32.0) để golden khớp.

## Quyết định (theo tiêu chí trong spec)

1. **OCR Windows:** **Windows OCR mặc định (đã chốt sau khi đo ảnh thật)**. RapidOCR quá chậm (~5 s) — tùy chọn, xem lại ở Phase 1.
2. **Model Windows:** tiêu chí spec là "vinai nếu đoạn ~50 từ beam 2 < 300 ms, không thì opus". vinai ~1.200 ms → **mặc định opus-mt-en-vi**, beam 2, `intra_threads=2`. vinai vẫn có trong cấu hình làm tùy chọn chất lượng cao.
3. **Android:** ONNX opus-mt, **CPU 2 luồng**, không XNNPACK, greedy. Không cần ML Kit Translation.
4. **Dung lượng thực tế:** CT2 opus 78 MB, CT2 vinai 439 MB, ONNX opus 131 MB.

## Cần người dùng quyết định

**Model mặc định trên Windows.** Số liệu cho thấy chế độ **Live** (1–2 câu thoại) với vinai mất ~260–300 ms/câu — vẫn nằm trong ngân sách Live < 400 ms nếu OCR nhanh — còn **phím tắt dịch đoạn ~50 từ** thì vinai vượt xa ngân sách 500 ms. Ba lựa chọn:

- **(a) opus mặc định** (đúng tiêu chí spec): nhanh nhất, nhưng dịch UI/câu dài kém.
- **(b) vinai mặc định cho Live, opus cho phím tắt:** chất lượng tốt nơi người dùng đọc nhiều nhất (thoại); tốn RAM cả hai model (~550 MB).
- **(c) vinai mặc định cho cả hai**, chấp nhận phím tắt chậm ~1–1,5 s với đoạn dài.

## Sửa sau review cuối Phase 0

- Input dài hơn 512 token (giới hạn của Marian) trước đây làm crash cả Python lẫn Kotlin → nay cắt còn 511 token + `</s>` (`MAX_SRC`); Kotlin giải phóng tensor khi encoder lỗi.
- Tokenizer Kotlin lệch spm `nmt_nfkc` ở một số ký tự (ZWSP, BOM, `▁`, 0x0B, 0x1C–0x1F, 0x85…) → đo trực tiếp spm và dùng đúng tập ký tự-thành-dấu-cách; thêm 23 ca khó vào `golden_tokenizer.json` (khớp 23/23).
- Kiểm tra "token ngôn ngữ lọt ra output" trước đây đếm trên chuỗi đã decode nên không bao giờ báo lỗi → nay đếm trên token thô.

## Quyết định của người dùng (2026-11-17)

**(c) vinai mặc định trên Windows cho cả Live và phím tắt.** Chấp nhận phím tắt dịch đoạn dài ~1–1,5 s để có bản dịch tốt hơn. opus-mt vẫn chọn được trong cấu hình.

## Việc mang sang Phase 1

- Sửa tên "III" bị đọc thành "Ill" (thuật ngữ game / quy tắc dòng tên).
- Thêm ảnh câu lựa chọn, menu, bong bóng thoại vào bộ đo khi có.
- Chốt model Windows theo lựa chọn ở trên.
- `onnxruntime` Python ghim 1.32.0 = `ortVersion` trong Gradle (giữ đồng bộ khi nâng cấp).
