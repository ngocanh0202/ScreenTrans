# Ảnh mẫu cho spike OCR

Cần 8–10 **ảnh chụp toàn màn hình** (điện thoại hoặc PC) của Reverse: 1999 (hoặc game khác) lúc đang có thoại, lưu `.png` hoặc `.jpg` vào thư mục này:

- có ảnh có **tên nhân vật** phía trên câu thoại,
- có ảnh có **câu lựa chọn**,
- có ảnh **nền mờ / nền rối** phía sau chữ,
- vài ảnh **menu / kho đồ / nhiệm vụ** (để đo chế độ toàn màn hình).

Không cần cắt ảnh và không cần gõ text: Claude cắt vùng khung thoại và tạo file `.txt` chứa chữ đúng để bạn kiểm tra.

Ảnh không được commit (gitignore). Chạy: `.venv\Scripts\python -m spikes.ocr.run`
