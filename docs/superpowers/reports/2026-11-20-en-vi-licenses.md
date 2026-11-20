# Giấy phép model và dữ liệu Anh–Việt (2026-11-20)

Mục đích: ScreenTrans là mã nguồn mở (AGPL-3.0) và phát hành model cho mọi người → model fine-tune (Phase 6) chỉ dùng dữ
liệu được phép huấn luyện **và** phát hành model dẫn xuất. Kiểm tra trên trang gốc (thẻ Hugging Face, README GitHub, mục
License trên opus.nlpl.eu, API OPUS cho kích thước en-vi) ngày 2026-11-20. **Không phải tư vấn pháp lý**; mục không xác
minh được đánh dấu *chưa xác minh*.

## Model đang phát hành

| Model | Giấy phép | Phân phối lại trong app mã nguồn mở |
|---|---|---|
| `Helsinki-NLP/opus-mt-en-vi` | Thẻ HF: apache-2.0; README OPUS-MT: CC-BY 4.0 cho model phát hành (hai nguồn khác nhau, đều thoáng) | Có, ghi công Helsinki-NLP / OPUS-MT. Fine-tune được phát hành theo Apache-2.0 / CC-BY 4.0 nếu dữ liệu thêm vào cho phép |
| `vinai/vinai-translate-en2vi-v2` | AGPL-3.0 (+ đề nghị trích dẫn bài báo INTERSPEECH 2022) | Có, theo AGPL-3.0 — repo này cũng AGPL-3.0. Fine-tune từ model này phải là AGPL |

## Dữ liệu

| Bộ dữ liệu | Giấy phép | Huấn luyện + phát hành model? | Cặp en-vi |
|---|---|---|---|
| ALT (Asian Language Treebank) | CC BY 4.0 | **Có** (ghi công) | 18K |
| Tatoeba | CC BY 2.0 FR | **Có** (ghi công) | 9,8K |
| translatewiki | CC BY 3.0 | **Có** (ghi công) | 47,7K |
| ELRC_2922 | CC BY 4.0 | **Có** (ghi công) | 4,3K |
| NLLB (OPUS) | ODC-By 1.0 (+ ràng buộc của nguồn gốc web) | Có cho phần biên soạn; văn bản thu từ web (rủi ro còn lại, phổ biến trong MT) | 50,1M |
| ParaCrawl-Bonus v9 | Đóng gói CC0, "không sở hữu văn bản" | Có cho đóng gói; văn bản thu từ web (rủi ro còn lại) | 6,3M |
| WikiMatrix / wikimedia / ELRC-wikipedia_health | CC-BY-SA | Có nhưng model có thể phải theo CC-BY-SA (vùng xám) | 1,07M / 768K / 126K |
| CCMatrix / CCAligned | Không ghi giấy phép | Không rõ | 50,1M / 12,4M |
| PhoMT | Thỏa thuận riêng: chỉ nghiên cứu / giáo dục, không phân phối lại | **Không** | ~3M |
| IWSLT'15, TED2020, NeuLab-TedTalks | CC BY-NC-ND (TED) | **Không** | 133K / 326K / 185K |
| QED | Chỉ cho nghiên cứu | **Không** | 338K |
| MTet (VietAI) | CC BY-NC-SA 4.0 | **Không** (phi thương mại) | 4,16M |
| OpenSubtitles | Không ghi; phụ đề có bản quyền bên thứ ba | **Không rõ, rủi ro cao** | 37M |
| ncduy/mt-en-vi (HF) | Gắn "mit" nhưng đóng gói lại OpenSubtitles / TED / QED… | **Không** (thẻ MIT không có giá trị) | 2,9M |

CC-BY-SA và model: CC nói ShareAlike chỉ áp dụng khi tác phẩm được sửa đổi và chia sẻ; việc model có phải "tác phẩm
phái sinh" hay không chưa ngã ngũ → an toàn: bỏ dữ liệu SA, hoặc phát hành model theo CC-BY-SA 4.0.

Dữ liệu sinh bởi LLM thương mại (Claude, Gemini, OpenAI): điều khoản của cả ba hạn chế dùng kết quả để phát triển mô hình
cạnh tranh → không dùng cho model phát hành; chỉ cung cấp công cụ để mỗi người tự tạo model riêng bằng key của mình.

## Kết luận cho Phase 6
- Model phát hành: fine-tune `opus-mt-en-vi` bằng ALT + Tatoeba + translatewiki + ELRC_2922 (sạch, nhỏ) + tập con lọc NLLB /
  ParaCrawl-Bonus (lớn, chấp nhận rủi ro web-crawl như thông lệ); phát hành Apache-2.0 / CC-BY 4.0 kèm ghi công.
- Model riêng: công cụ sinh dữ liệu bằng LLM + `corrections.jsonl`, không đưa dữ liệu / model đó vào repo.
