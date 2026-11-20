# Fixtures sửa bảng thuật ngữ (Cài đặt → Thuật ngữ)

Luật (`windows/app/text/term_edit.py` là chuẩn, Kotlin `TermEdit.kt` pass cùng bộ). Một dòng = `[nguồn, đích, phân biệt hoa thường]`;
`đích` = `null` nghĩa là **giữ nguyên** (`keep`), có chữ là **dịch cố định** (`map`).

## `parse.json` — đọc file thuật ngữ của game
`text`: nội dung file. `rows`: các dòng đọc được, hoặc `null` = file hỏng (không phải JSON object có `entries` là mảng).
Mục không phải object hoặc thiếu `source` (chuỗi) bị bỏ qua; `target` chỉ lấy khi `type` = `map` và là chuỗi;
`case_sensitive` mặc định `true`.

## `clean.json` — trước khi lưu
- Nguồn: bỏ khoảng trắng hai đầu, gộp khoảng trắng giữa; nguồn rỗng → bỏ dòng.
- Đích: bỏ khoảng trắng hai đầu; rỗng → `null` (giữ nguyên).
- Trùng nguồn (không phân biệt hoa thường) → dòng **sau** thay dòng trước, ở **vị trí của dòng trước**.

Khi lưu: `{"entries": [{"source", "type": "keep"|"map", "target" (chỉ khi map), "case_sensitive"}]}`.
