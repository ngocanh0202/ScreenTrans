# OpenCV trước Windows OCR — có giúp đọc chữ game không? (2026-11-20)

Câu hỏi của người dùng: OCR hiện tại có chỗ không xử lý được thì thêm OpenCV xử lý ảnh trước khi OCR.
Script: `spikes/ocr/preprocess.py` (`.venv\Scripts\python -m spikes.ocr.preprocess --hard <thư mục>`).

## Dữ liệu
- 5 ảnh cắt khung thoại Reverse: 1999 có chữ đúng (`spikes/ocr/data/rv_*.png`): CER cả đoạn.
- 6 ảnh toàn màn hình (`spikes/ocr/data/full`): số dòng mong đợi đọc được (CER ≤ 0.1), tổng 37 dòng.
- 2 ảnh khó từ máy người dùng: cắt cảnh chữ máy đánh bị mờ, khung thoại (8 dòng).

## Kết quả (Windows OCR)

| Xử lý ảnh | CER ảnh cắt | Dòng đọc được (toàn màn hình) | Ảnh khó | ms / ảnh toàn màn hình |
|---|---|---|---|---|
| **Không (hiện tại)** | **0.024** | **30/37** | **7/8** | **305** |
| Phóng to ×2 | 0.024 | 30/37 | 7/8 | 559 |
| CLAHE (tăng tương phản) | 0.024 | 23/37 | 6/8 | 261 |
| ×2 + làm nét | 0.024 | 22/37 | 7/8 | 641 |
| ×2 + nhị phân Otsu | 0.024 | 30/37 | 4/8 | 646 |
| ×2 + CLAHE + làm nét | 0.043 | 20/37 | 5/8 | 764 |

Không cách nào tốt hơn ảnh gốc; phần lớn tệ hơn và chậm hơn 2×.

## Những dòng ảnh gốc bỏ sót
- `AUTO`, `SKIP` — nhãn nút, Live vốn lọc bỏ.
- `Druvis III` → `Druvis Ill` (5 lần) — số La Mã: sửa bằng hậu xử lý chữ, không phải xử lý ảnh.
- `Committee Member I` — ảnh chụp có lớp bản dịch của app đè lên (khi chụp thật lớp này bị loại khỏi ảnh).

## Kết luận
Không thêm OpenCV (≈118 MB trên Windows, vài chục MB trên Android, chậm hơn, kết quả kém hơn). Lỗi "bản dịch nhảy
lên xuống, to nhỏ" là do vị trí / cỡ chữ đo lại mỗi lần OCR — đã sửa bằng cách giữ khung và cỡ chữ ổn định
(`style.steady_box` / `steady_font`). Việc nên làm tiếp: luật hậu xử lý `Ill`/`Il` sau một tên viết hoa → `III`/`II`.
