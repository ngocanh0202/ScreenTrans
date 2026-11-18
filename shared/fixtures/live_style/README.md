# Fixtures kiểu chữ "giống game" (BlockStyle.sample)

Mỗi file: ảnh nhỏ của **một khối chữ** (`pixels`: `height` hàng × `width` ô, màu `rrggbb`), `expected`: màu chữ và
màu nền lấy mẫu được (sai số ±8 mỗi kênh), hoặc `null` = không lấy được → dùng kiểu "dễ đọc" (chữ trắng nền tối).

Luật (`windows/app/live/style.py` là chuẩn, Kotlin `BlockStyle.kt` pass cùng bộ):
- **Nền** = trung vị từng kênh của các điểm trên **viền 2 px** của khối.
- Viền không đều (độ lệch chuẩn độ sáng của viền > 24) → `null`.
- **Chữ** = trung vị từng kênh của 15% điểm bên trong (bỏ viền) **xa màu nền nhất** (khoảng cách RGB).
- Tỉ lệ tương phản WCAG giữa chữ và nền < 3 → `null`.
