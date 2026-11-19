# Fixtures lọc khối chữ Live (bỏ chữ rác trước khi dịch)

Mỗi case: một khối (đoạn sau hậu xử lý) với `text`, `kind`, `box` [l, t, r, b], `line_height`; `keep` = có dịch / vẽ không.
Python `windows/app/live/filter.py` là chuẩn, Kotlin `LiveFilter.kt` pass cùng bộ. Luật (khối `name` luôn giữ):
- Bỏ nếu có ít hơn 3 chữ cái (2 nếu kết thúc bằng `.` `!` `?` `…`: "No."), hoặc chữ cái < 50% số ký tự không phải khoảng trắng.
- Bỏ nếu khối chỉ có ≤ 3 từ mà có một từ trộn chữ cái và chữ số (`St3loo 3,` — nhiễu OCR; câu dài hơn có một chữ đọc nhầm như `cl0sing`, hay `2nd`, vẫn giữ), hoặc một từ chỉ là số mà khối chỉ có ≤ 2 từ (`Level 23`).
- Bỏ nếu chỉ một từ và không kết thúc bằng `.` `!` `?` `…` (nhãn nút: AUTO, SKIP).
- Bỏ nếu không có từ nào dài ≥ 2 chữ cái (`X X X`).
- Bỏ nếu khối hẹp hơn 3 × chiều cao dòng (chữ dọc / nhiễu), khi biết chiều cao dòng.
