# Fixtures hồ sơ game (Python ↔ Kotlin)

`input`: nội dung file hồ sơ (object JSON, hoặc chuỗi = văn bản thô của file). `expected`: hồ sơ sau khi đọc và chuẩn hóa,
ghi lại đủ mọi trường (`null` = không đọc được → app dùng hồ sơ mặc định).

Luật đọc (`windows/app/profiles.py` là chuẩn, Kotlin `Profile.parse` pass cùng bộ):
- Không phải JSON / không phải object / thiếu `id` (chuỗi khác rỗng) → `null`.
- `name`: chuỗi, mặc định `""`. `glossary`: chuỗi hoặc `null`.
- `live.style` ∈ `match` (giống game: cỡ chữ + màu lấy từ chữ gốc) | `classic` (chữ trắng nền tối); khác → `match`.
- `live.scope` ∈ `screen` | `region` (khác → `region`); `interval_ms`, `settle_ms` số nguyên > 0, `change_threshold` số > 0
  (sai kiểu / ≤ 0 → mặc định 300 / 250 / 5.0).
- `regions`, `ignore_regions`: danh sách `[x, y, w, h]` tương đối 0–1. Phần tử không phải 4 số → bỏ. `x`, `y` kẹp vào [0, 1];
  `w`, `h` kẹp vào [0, 1 − x] / [0, 1 − y]; sau khi kẹp `w ≤ 0` hoặc `h ≤ 0` → bỏ. Không phải danh sách → `[]`.
- `overrides`: object chuỗi → chuỗi; khóa được gộp khoảng trắng; khóa rỗng hoặc giá trị không phải chuỗi → bỏ.
