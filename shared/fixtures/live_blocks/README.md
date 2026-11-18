# Fixtures Live vùng lớn (BlockTracker)

Mỗi bước đưa danh sách đoạn chữ (sau hậu xử lý) của vùng lớn; bộ theo dõi trả `added` / `kept` / `removed`
(so theo **text**, thứ tự trên→dưới rồi trái→phải).

- Chỉ giữ **`max_blocks`** đoạn đầu tiên theo `(top, left)`.
- Một đoạn mới **giữ nguyên** một khối đang hiện khi text đã gộp khoảng trắng giống hệt **và** tâm hai hộp cách nhau
  ≤ `near_px` (khoảng cách Euclid). Ghép tham lam theo thứ tự đoạn mới; mỗi khối cũ ghép tối đa một lần.
- Chưa ghép được: đoạn mới **giữ key** của một khối đang hiện khi **góc trên-trái** hai hộp cách nhau ≤ `near_px` **và** text cũ
  (đã gộp khoảng trắng) là **tiền tố thực sự** của text mới → `grown` (chữ đang chạy dài thêm, có thể xuống dòng). Từ **cuối** của text cũ được phép khác (chữ vẽ dở / OCR đọc sai):
  text mới bắt đầu bằng text cũ bỏ từ cuối + dấu cách, và không ngắn hơn text cũ quá 3 ký tự. Text giống hệt không tính là `grown`.
- Đoạn mới không ghép được → `added`; khối cũ không ghép được → `removed`. Khối được giữ nguyên giữ **key** cũ.
