# Huấn luyện model dịch (Phase 6)

Tinh chỉnh `Helsinki-NLP/opus-mt-en-vi` (75M — nhanh như model đang chạy trên điện thoại) để dịch thoại game tốt hơn.
Giấy phép dữ liệu: [báo cáo](../docs/superpowers/reports/2026-11-20-en-vi-licenses.md).

## Model dùng chung (dữ liệu mở — được phát hành)

1. Tạo notebook trên [Kaggle](https://www.kaggle.com/code) → File → Import notebook → `training/kaggle_finetune.ipynb`.
2. Settings: **Accelerator: GPU T4 x2** (hoặc P100), **Internet: On**.
3. (Tùy chọn, để phát hành) Add-ons → Secrets: `HF_TOKEN` (token ghi của Hugging Face), đặt `PUSH_TO` trong ô cài đặt.
4. **Run all**. Tải + lọc dữ liệu ~20–40 phút, huấn luyện vài giờ (phiên Kaggle tối đa 12 giờ). Notebook in điểm
   chrF / BLEU của model gốc và model mới, và các câu thoại mẫu dịch cạnh nhau (CŨ / MỚI).
5. Tải `screentrans-en-vi.zip` (Output) về, giải nén, rồi trên máy:

   ```
   .venv\Scripts\python -m models.export ct2  screentrans-en-vi --hf-id D:\path\screentrans-en-vi    # Windows
   .venv\Scripts\python -m models.export onnx screentrans-en-vi --hf-id D:\path\screentrans-en-vi    # Android
   ```

Dữ liệu dùng: ALT, Tatoeba, translatewiki, ELRC_2922 (CC BY, ghi công) + tập con đã lọc của NLLB (ODC-By) và
ParaCrawl-Bonus (CC0 đóng gói). Không dùng PhoMT, TED/IWSLT, QED, MTet, OpenSubtitles. `DATA_LICENSES.md` được ghi kèm model.

## Model riêng (dữ liệu từ LLM — chỉ dùng cho bạn, **không phát hành**)

Điều khoản của Anthropic / Google / OpenAI không cho dùng kết quả của họ để làm mô hình cạnh tranh: dữ liệu và model
này chỉ để bạn dùng, không đưa lên repo hay Hugging Face công khai.

```
# 1. ước tính trước (không gửi gì)
.venv\Scripts\python -m training.distill_data --engine gemini --sentences cau_thoai.txt --from-log --with-corrections --out D:\my-data
# 2. chạy thật (key lấy từ Cài đặt → Dịch bằng, hoặc biến môi trường SCREENTRANS_KEY), có giới hạn ký tự
.venv\Scripts\python -m training.distill_data --engine gemini --sentences cau_thoai.txt --from-log --with-corrections --out D:\my-data --yes --budget-chars 2000000
```

Có thể chạy nhiều lần: câu đã dịch được bỏ qua. Tải `D:\my-data\distilled.tsv` lên Kaggle (Dataset riêng tư), đặt
`EXTRA_TSV` trong notebook; notebook sẽ không đẩy model này lên Hugging Face.
