# Fixtures nhớ màu "giống game" theo vị trí

Lấy màu lại cho mỗi khối chữ mới làm màu bản dịch đổi liên tục (lấy lúc chữ game đang hiện dần / gõ, hoặc lúc lấy
không được → chữ trắng nền tối rồi lại màu game). Luật (`windows/app/live/style.py` `style_cell` là chuẩn, Kotlin
`BlockStyle.styleCell` pass cùng bộ):

- Vùng Live chia lưới **6 × 6**; ô của một khối = ô chứa góc trên-trái của khối: `cột = min(5, floor(trái × 6 / rộng))`,
  `hàng = min(5, floor(trên × 6 / cao))` (âm → 0); khóa = `loại:cột:hàng` (`loại`: `text` / `name`).
- Mỗi lượt Live: ô đã lấy được màu thì mọi khối sau trong ô đó (cùng loại) dùng **đúng màu đó**; lấy không được
  (`null`) thì không nhớ, lần đọc sau lấy lại.
