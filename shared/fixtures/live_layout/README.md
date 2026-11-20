# Fixtures bố cục khung bản dịch Live

Luật (`windows/app/live/layout.py` là chuẩn, Kotlin `Layout.kt` pass cùng bộ). Đơn vị: pixel.

## `widen.json` — độ rộng khung
Khung bản dịch mặc định rộng bằng chữ gốc (`width`). Câu tiếng Việt thường dài hơn: chữ gốc ngắn ("Hello") làm
bản dịch ("Xin chào") rớt chữ cuối xuống dòng. Luật:
- Giới hạn `cap = min(room, width + max(0.25 × width, 4 × px))` (`room`: chỗ tới mép phải màn hình, `px`: cỡ chữ).
- Nếu khung rộng `cap` không ít dòng hơn khung rộng `width` → giữ `width`.
- Ngược lại → độ rộng **nhỏ nhất** trong `[width, cap]` cho cùng số dòng như `cap`.

Trong fixtures, số dòng = xuống dòng tham lam theo từ: `words` là độ rộng từng từ, `space` độ rộng khoảng trắng;
một từ rộng hơn cả khung vẫn chiếm một dòng riêng.

## `separate.json` — không chồng nhau
`rects`: các khung `[trái, trên, phải, dưới]` (phải / dưới không tính). Xét theo thứ tự `trên` rồi `trái`; khung đè lên
một khung đã đặt (giao nhau thật, diện tích > 0) được đẩy xuống ngay dưới khung đó + `gap`, giữ nguyên chiều cao,
lặp tới khi không còn đè. `expected`: các khung theo **đúng thứ tự đầu vào**.
