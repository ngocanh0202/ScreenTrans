# Fixtures danh sách model (Cài đặt → Model)

Luật (`windows/app/model_catalog.py` là chuẩn, Kotlin `ModelCatalog.kt` pass cùng bộ).

Đầu vào:
- `manifest`: các model trong `manifest.json` **của nền tảng này** (`id`, `version`, `label`, `files` với `size`).
- `installed`: model đã có trên máy, `id` → các phiên bản đã tải xong (có `.complete`).
- `bundled`: (Android) `id` → phiên bản nhúng sẵn trong APK, luôn dùng được, không xóa được.
- `active`: model đang dùng.

Đầu ra `rows` (thứ tự: model trong manifest trước, theo thứ tự manifest; rồi model chỉ có trên máy, theo `id`):
- `status`:
  - `bundled`: nhúng sẵn và manifest không có bản khác bản nhúng (hoặc không có trong manifest);
  - `update`: đã có (tải về hoặc nhúng sẵn) nhưng phiên bản mới nhất trong manifest chưa có trên máy;
  - `installed`: đã có phiên bản của manifest, hoặc model chỉ có trên máy (thêm từ thư mục);
  - `missing`: chưa có.
- `version`: phiên bản sẽ dùng trên máy (bản tải về mới nhất theo thứ tự chuỗi, không có thì bản nhúng), `null` khi chưa có.
- `latest`: phiên bản trong manifest (`null` nếu không có trong manifest).
- `download`: tổng `size` cần tải (0 khi `installed` / `bundled`).
- `deletable`: có bản tải về trên máy (bản nhúng không xóa được).
- `active`: `id` == `active`.
- `label`: từ manifest, không có thì `id`.
