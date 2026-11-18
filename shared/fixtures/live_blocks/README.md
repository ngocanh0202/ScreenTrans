# Fixtures Live vùng lớn (BlockTracker)

Mỗi bước đưa danh sách đoạn chữ (sau hậu xử lý) của vùng lớn; bộ theo dõi trả `added` / `kept` / `removed`
(so theo **text**, thứ tự trên→dưới rồi trái→phải).

- Chỉ giữ **`max_blocks`** đoạn đầu tiên theo `(top, left)`.
- Một đoạn mới **giữ nguyên** một khối đang hiện khi text đã gộp khoảng trắng giống hệt **và** tâm hai hộp cách nhau
  ≤ `near_px` (khoảng cách Euclid). Ghép tham lam theo thứ tự đoạn mới; mỗi khối cũ ghép tối đa một lần.
- Đoạn mới không ghép được → `added`; khối cũ không ghép được → `removed`. Khối được giữ nguyên giữ **key** cũ.
