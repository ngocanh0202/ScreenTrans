# Fixtures hậu xử lý (dùng chung Python ↔ Kotlin)

Mỗi file `*.json`:

```json
{
  "name": "mô tả ngắn",
  "lines": [{"text": "dòng OCR", "box": [left, top, width, height]}],
  "expected": [{"kind": "name" | "text", "text": "đoạn sau xử lý", "sentences": ["câu 1", "..."]}]
}
```

`sentences` của đoạn `name` luôn là `[]`. Box lấy từ Windows OCR thật trên ảnh Reverse: 1999 khi có (ghi trong `name`).

## Quy tắc (bản Python `windows/app/text/postprocess.py` là chuẩn)

`h` = trung vị chiều cao các dòng (sau bước 1).

1. **Làm sạch dòng:** bỏ token đầu/cuối dòng không có chữ cái hoặc chữ số, và token đầu dòng dài ≤ 2 ký tự có chứa một trong `()[]{}<>|©®` (biểu tượng nút bị OCR đọc nhầm, vd `"(D Druvis Ill:"` → `"Druvis Ill:"`). Sau đó bỏ dòng không còn chữ cái nào hoặc chỉ còn 1 ký tự.
2. **Nhóm đoạn:** duyệt dòng theo `top` tăng dần. Dòng nối vào một đoạn đã có nếu `0 - 0.5h <= line.top - para.bottom <= 0.8h` **và** `para.left - h <= line.left <= para.right`. Nếu nhiều đoạn thỏa, chọn đoạn có `bottom` lớn nhất. Không thỏa → đoạn mới. (Khung thoại: khoảng cách dòng ~0.3h; màn hình Log: ~0.73h giữa các dòng cùng đoạn, ~2.8h giữa các đoạn; tên → thoại: ~1.2h.)
3. **Nối dòng:** bằng 1 dấu cách; dòng kết thúc bằng `[a-z]-` và dòng sau bắt đầu bằng chữ thường → nối liền, bỏ `-`. Chuẩn hóa khoảng trắng.
4. **Tên nhân vật:** đoạn chỉ 1 dòng, ≤ 3 token, mỗi token bắt đầu bằng chữ hoa hoặc khớp `^[IVXLl1|]{1,4}$`, **và** (text kết thúc bằng `:` **hoặc** (không kết thúc bằng dấu câu trong `.!?,;…"'”’` **và** có đoạn khác với `0 <= other.top - para.bottom <= 2h` và `other.left < para.right + h` và `other.right > para.left - h`)) → `kind = "name"`. Bỏ `:` cuối; token khớp `^[Il1|]{2,4}$` → `"I" * len` (`"Druvis Ill"` → `"Druvis III"`).
5. **Thứ tự kết quả:** sắp đoạn theo `top`; hai đoạn liền nhau có `|top chênh| < 0.5h` thì đoạn có `left` nhỏ hơn đứng trước.
6. **Tách câu** (đoạn `text`): cắt sau một chuỗi `[.!?…]+` (có thể kèm `"”’'` đóng) khi theo sau là khoảng trắng rồi chữ hoa hoặc `"“`. Không cắt khi token kết thúc ở đó là `Mr. Mrs. Ms. Dr. St. vs. etc.` hoặc là một chữ cái hoa đứng một mình + `.`.

## Chi tiết bắt buộc cho bản port (Kotlin phải làm y hệt)

- **Duyệt dòng:** sắp theo `(top, left)` tăng dần. Khi một dòng nối được vào nhiều đoạn có cùng `bottom` lớn nhất → chọn **đoạn được tạo trước** (fixture `tie_break_two_groups`).
- **"Chữ hoa"**: quy tắc 4 (token tên) và phép thử "một chữ cái hoa + `.`" của quy tắc 6 dùng **ASCII `A`–`Z`** — `Élise` không phải tên (fixture `accented_name`). Ký tự **mở đầu câu sau** ở quy tắc 6 dùng chữ hoa **Unicode** (Python `str.isupper()`, Kotlin `Char.isUpperCase()`). Nối gạch ngang (quy tắc 3): chữ thường **ASCII** `[a-z]` trước `-`, ký tự đầu dòng sau là chữ thường **Unicode**.
- **"Chữ cái/chữ số"** ở quy tắc 1 theo Unicode (Python `str.isalpha()` / `str.isalnum()`; Kotlin `Char.isLetter()` / `Char.isLetterOrDigit()`). Khác biệt đã biết: Python coi chữ số mũ/phân số như `²`, `½` là `isalnum`, Kotlin `isLetterOrDigit` thì không — OCR game hiếm gặp, chấp nhận.
- **Tách token** theo khoảng trắng Unicode (Python `str.split()`; Kotlin `trim().split(Regex("(?U)\s+"))`).
- **Quy tắc 6:** trước khi so với danh sách viết tắt và quy tắc "một chữ hoa + `.`", bỏ các ký tự mở đầu token trong `"“‘'(` (fixture `quote_prefixed_abbrev`: `"Mr. Smith came."` không bị tách sau `"Mr.`).
- **Quy tắc 4:** bỏ `:` cuối **trước** khi đếm token (fixture `name_with_colon_three_tokens`: `Old Man Tom:` → tên `Old Man Tom`).

## Chữ nghiêng

Mỗi dòng có thể có `angle` (độ, chiều kim đồng hồ dương; mặc định 0) và hộp `box` tính **trong hệ trục đã xoay −angle quanh gốc ảnh**
(bộ chuyển OCR làm việc xoay thẳng). Luật:
- Dòng có |angle| > 60° bị bỏ (chữ dọc / nhiễu).
- Các dòng được chia nhóm theo góc (sắp theo góc, một nhóm gồm các dòng lệch ≤ 2° so với dòng đầu nhóm); |góc trung vị| < 2° → nhóm thẳng (angle 0).
- Mỗi nhóm chạy đúng các luật ở trên; mỗi đoạn mang `angle` của nhóm. Các nhóm nối tiếp nhau theo vị trí trên màn hình (đỉnh của đoạn đầu
  tiên sau khi xoay lại), nên một nhóm duy nhất cho kết quả như trước.
- Trong `expected`, trường `angle` chỉ được so khi có mặt.
