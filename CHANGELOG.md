# Changelog

## Chưa phát hành

- **Dịch bằng mô hình lớn qua mạng (Windows)**: chọn theo game trong Cài đặt → "Dịch bằng": Gemini, OpenAI, Claude (mặc định `claude-opus-5-5`, đổi được) hoặc server Kaggle riêng (`training/kaggle_serve.ipynb`). Gửi kèm 3 câu trước, người nói và thuật ngữ của game; Live gom các câu của một lần đọc vào một lần gọi. Lỗi / quá thời gian (Live 2,5 s, dịch 1 lần 6 s) / hết hạn mức → dùng model trên máy ngay, thử lại server sau 30 s; sai key → báo, không thử lại. Key mã hóa DPAPI; giới hạn ký tự mỗi ngày.
- **Bản dịch luôn hiện đủ**: không cắt bằng "…" nữa, bỏ nút ⤢ (Android). Khung giữ cỡ chữ gốc và dài ra theo nội dung, được tràn ra ngoài chữ gốc; gần đáy màn hình thì đẩy lên. Chế độ "Thu nhỏ chữ" thu nhỏ trước, nhỏ hết mức thì cũng tràn ra. Áp dụng cho Live và dịch toàn màn hình.
- **Chọn bộ OCR theo game**: Windows OCR / RapidOCR (Windows, RapidOCR cài thêm), ML Kit (Android).
- **Live**: nhận ra lời thoại mới (đếm ô ảnh đổi thay vì trung bình cả ảnh — trước đây chỉ dịch câu đầu); bản dịch nhích lên một chút; câu đã dịch hiện lại ngay; Android không còn báo "Không thấy hình game" ở các cảnh chuyển màu đen.

## v0.1.0

Bản phát hành đầu tiên: OCR màn hình và dịch Anh → Việt ngay trên máy, cho Windows và Android.

**Cài đặt**
- Windows 10/11: giải nén `ScreenTrans-windows.zip`, chạy `ScreenTrans.exe` (biểu tượng **T** ở khay hệ thống). Lần đầu tự tải model vinai (~440 MB). Cần gói English OCR của Windows.
- Android 10+: cài `ScreenTrans-android.apk` (model có sẵn). Khi Android hỏi quyền ghi màn hình, chọn **"Một ứng dụng" → game** để bản dịch Live không nháy.

**Tính năng**
- Dịch vùng (`Ctrl+Alt+T` / nút nổi → "Dịch vùng"), dịch toàn màn hình một lần (`Ctrl+Alt+F` / "Toàn màn hình").
- **Live** (`Ctrl+Alt+L` / "Bật Live"): tự dịch khi chữ đổi, bản dịch đè lên đúng chỗ chữ gốc, hiện **từng câu ngay khi câu đó hiện xong**; phạm vi **Toàn màn hình** hoặc **Vùng** (nhiều vùng, vùng bỏ qua).
- **Hồ sơ theo game**: tự nhận game (Windows: cửa sổ đang mở; Android: Usage Access hoặc chọn tay), lưu vùng, phạm vi Live, tham số và bản sửa riêng từng game; vùng đi theo cửa sổ game.
- **Sửa bản dịch** (`Ctrl+Alt+E` / "Sửa bản dịch gần nhất" / nút "Sửa"): lần sau gặp đúng câu sẽ dùng bản của bạn; thêm thuật ngữ giữ nguyên / dịch cố định; ghi `corrections.jsonl`.
- Bảng thuật ngữ chung + theo game, tự giữ nguyên tên riêng lặp lại; cache bản dịch (khóa theo model + phiên bản + thuật ngữ).
