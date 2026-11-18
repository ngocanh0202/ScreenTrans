# Changelog

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
