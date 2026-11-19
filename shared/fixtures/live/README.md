# Fixtures Live (dùng chung Python ↔ Kotlin)

Máy trạng thái Live quyết định **khi nào OCR** và **có dịch kết quả OCR không**. Bản Python `windows/app/live/machine.py` là chuẩn; bản Kotlin `android/app-core/.../live/LiveMachine.kt` phải pass cùng các file ở đây.

```json
{
  "name": "mô tả",
  "params": {"interval_ms": 300, "active_interval_ms": 100, "settle_ms": 250, "max_wait_ms": 2000, "change_threshold": 5},
  "events": [
    {"t": 0, "diff": 20.0},
    {"t": 1250, "ocr_text": "We have to leave."},
    {"t": 50, "overlay_changed": true}
  ],
  "expected": [{"t": 1200, "action": "ocr"}, {"t": 1250, "action": "translate"}]
}
```

`params` tùy chọn (mặc định như trên, `partial_interval_ms` mặc định `0` = tắt). `events` theo thứ tự thời gian; `expected` liệt kê **mọi** hành động khác "chờ", theo thứ tự.

## Quy tắc

`diff` = **số ô** có độ xám lệch quá 16 (0–255) giữa ảnh xám thu nhỏ rộng 160 px của khung này và khung **ngay trước** (trung bình cả ảnh làm mất dòng thoại mới trên toàn màn hình). "Đổi" nghĩa là `diff > change_threshold`.

- **Bỏ qua thay đổi do chính overlay:** sau `overlay_changed`, khung kế tiếp không được xét (chỉ làm mốc mới).
- **ĐỨNG YÊN:** khung "đổi" → sang **ĐANG ĐỔI**, ghi `changed_at = last_change = t`.
- **ĐANG ĐỔI:** khung "đổi" → `last_change = t`. Sau đó, nếu `t - last_change >= settle_ms` → **OCR** (lý do *settled*); ngược lại nếu `t - changed_at >= max_wait_ms` → **OCR** (lý do *max_wait*). OCR xong → về **ĐỨNG YÊN**.
- **Kết quả OCR** (`ocr_text`), text chuẩn hóa = gộp khoảng trắng:
  1. rỗng → **skip**;
  2. giống text **đã dịch gần nhất** → **skip**;
  3. lý do *max_wait* và khác text OCR lần trước → **wait**: quay lại ĐANG ĐỔI với `changed_at = t` (chữ có thể còn đang chạy; dịch khi chữ đứng yên hoặc khi lần OCR sau ra y hệt);
  4. còn lại → **translate** (ghi nhớ là text đã dịch).
- **OCR giữa chừng** (`partial_interval_ms` > 0, Live realtime từng câu): khi đang ĐANG ĐỔI và chưa tới OCR ở trên, nếu
  `t - max(changed_at, lần PARTIAL trước) >= partial_interval_ms` → **PARTIAL** (ghi `"action": "partial"`), trạng thái giữ nguyên.
  Kết quả OCR giữa chừng không đi qua `ocr_text` (đi vào cổng câu, xem `shared/fixtures/live_sentences`).
- Nhịp chụp: `active_interval_ms` khi ĐANG ĐỔI, `interval_ms` khi ĐỨNG YÊN.
