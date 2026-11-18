# Fixtures câu đã xong (SentenceGate, Live realtime từng câu)

Mỗi bước: danh sách câu (sau hậu xử lý) của **một khối** ở một lần OCR, `final` (chữ đã dừng hẳn) và `done` = số câu đầu
được coi là **xong** (được dịch và hiện). `previous` = danh sách câu của bước trước (bước đầu: không có).

- `final` → mọi câu xong.
- Mọi câu **không phải câu cuối** đều xong (đã có câu sau).
- Câu cuối xong khi kết thúc bằng `.` `!` `?` `…` (có thể kèm `"` `'` `”` `’` `)` `」` `』` sau đó) **và** giống hệt câu cuối
  của `previous` với cùng số câu.
- Bản Python `windows/app/live/sentences.py` là chuẩn; Kotlin `SentenceGate.kt` pass cùng bộ.
