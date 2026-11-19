# Phase 4c — Chữ nghiêng, cài đặt Windows, lỗi nhỏ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chữ nghiêng trên màn hình (vd bảng nhiệm vụ Reverse: 1999) được nhóm, dịch đúng và **bản dịch vẽ nghiêng theo chữ gốc** trên Windows + Android; Windows có cửa sổ cài đặt; dọn các lỗi nhỏ của Phase 4b.

**Architecture:** Bộ chuyển OCR (ML Kit / Windows OCR) **xoay thẳng** mỗi dòng nghiêng: tọa độ dòng được biểu diễn trong hệ trục đã xoay `-angle` quanh gốc ảnh (0, 0), kèm `angle`. Hậu xử lý nhóm riêng các dòng cùng góc (chênh ≤ 2°) rồi chạy y như chữ thẳng; `Paragraph.angle` đi theo. Overlay vẽ khối trong hệ trục xoay: `rotate(angle)` quanh gốc ảnh rồi vẽ hình chữ nhật như cũ. Góc < 2° coi như 0.

**Tech Stack:** Python 3.11 + PySide6 + winocr, Kotlin + ML Kit 16.0.1 (`Line.angle`, `cornerPoints`), pytest / JUnit 5, fixtures dùng chung.

**Spec:** [AGENT.md](../../../AGENT.md) Phase 4c (người dùng chọn 2026-11-19: "hiển thị chữ nghiêng trên màn hình thì bản dịch cũng phải nghiêng theo").

## Global Constraints

- Góc theo độ, chiều kim đồng hồ dương (như ML Kit); |góc| < 2° → 0 (không xoay); dòng gần dọc (|góc| > 60°) → bỏ qua (không dịch).
- Hệ trục khối nghiêng: điểm ảnh `(x, y)` → hệ thẳng `(x cosθ + y sinθ, −x sinθ + y cosθ)` với θ = góc (xoay `−θ` quanh (0, 0)); vẽ lại bằng phép xoay `+θ` quanh gốc ảnh.
- Các dòng chỉ được ghép đoạn với dòng cùng góc (chênh ≤ 2°); thứ tự đoạn: theo `(top, left)` trong hệ của chính nó, rồi các nhóm góc theo vị trí tâm trên màn hình.
- Fixtures hậu xử lý thêm trường `angle` (mặc định 0); bản Python là chuẩn, Kotlin pass cùng bộ.
- Mọi thứ đang có (chữ thẳng) giữ nguyên kết quả: fixtures cũ không đổi.

## Review Focus

1. **Hai khối khác góc gần nhau** (bảng nghiêng chồng lên khung thoại thẳng) → không bị ghép chung một đoạn. Fixture ở Task 1.
2. **Bản dịch nghiêng tràn ra ngoài màn hình** → vẫn nằm trong màn hình, ô ⤢ (Android) đặt ở góc thật của khung đã xoay. Test ở Task 3.
3. **Chữ dọc / gần dọc** (> 60°) → bỏ qua, không vẽ chữ dọc từng ký tự. Fixture ở Task 1.
4. **Lấy màu "giống game" cho khối nghiêng** → cắt ảnh theo khung bao của khung đã xoay, không lỗi chỉ số. Test ở Task 2.
5. **Theo dõi khối khi chữ nghiêng dài thêm** → vẫn `grown` (so trong hệ trục xoay). Test ở Task 1.

---

### Task 1: Dòng nghiêng — dữ liệu, xoay thẳng, hậu xử lý (Python + Kotlin)

**Files:** Modify `windows/app/ocr/base.py` (`Line.angle`), `windows/app/text/postprocess.py`, `android/text-core/.../Postprocess.kt`; Create `windows/app/ocr/deskew.py`, `android/text-core/.../Deskew.kt`; fixtures `shared/fixtures/postprocess/tilted_*.json`; Test `windows/tests/test_postprocess.py`, `windows/tests/test_deskew.py`, Kotlin `PostprocessFixturesTest`, `DeskewTest`

**Interfaces:**
- `Line(text, left, top, width, height, angle=0.0)` — hộp trong hệ trục đã xoay theo `angle`. `Paragraph(..., line_height, angle=0.0)`.
- `deskew.from_corners(points: list[(x, y)] (4 điểm, theo chiều kim đồng hồ từ trên-trái), angle) -> (left, top, width, height)`; `deskew.from_words(word_rects: list[(x, y, w, h)]) -> (angle, left, top, width, height)` (góc = độ dốc tâm từ đầu → từ cuối; < 2° → 0).
- `rotate_point(x, y, angle) -> (x', y')` (xoay `−angle`), `unrotate_point` (ngược lại); `bounds(box, angle) -> (l, t, r, b)` khung bao thẳng của hộp xoay (để cắt ảnh lấy màu).
- `postprocess(lines)`: chia dòng theo góc (cụm ≤ 2°), bỏ cụm > 60°, chạy quy tắc cũ trên mỗi cụm, `Paragraph.angle` = góc trung vị của cụm.
- [ ] **Step 1:** Fixtures: `tilted_two_lines_one_paragraph` (2 dòng 15° → 1 đoạn), `tilted_next_to_straight` (khối 15° cạnh khối 0° → 2 đoạn), `near_vertical_dropped` (70° → bỏ). Test deskew: hình chữ nhật 200×30 xoay 15° → `from_corners` trả lại 200×30; `from_words` 3 từ dọc theo đường dốc 10° → góc 10±0,5. FAIL → implement Python → PASS → port Kotlin → PASS. Commit `feat(text): tilted lines (deskew + per-angle grouping)`.

### Task 2: Windows — OCR nghiêng + vẽ nghiêng

**Files:** Modify `windows/app/ocr/windows_ocr.py`, `windows/app/live/controller.py` (cắt ảnh theo `bounds`), `windows/app/gui/live_overlay.py`, `windows/app/gui/fullscreen.py`, `windows/app/pipeline.py` (`Segment.angle`); Test `windows/tests/test_windows_ocr.py` (hàm chuyển từ từ → dòng, không cần OCR thật), `test_live_parts.py`, `test_fullscreen.py`, `test_live_controller.py`

- Live và toàn màn hình một lần: khối có `angle` ≠ 0 vẽ bằng `painter.translate(gốc ảnh) ; rotate(angle) ;` rồi vẽ hình chữ nhật hệ thẳng (đổi sang logic px theo DPR).
- [ ] **Step 1:** Test: dòng từ các từ nghiêng 12° → `Line.angle≈12`; overlay khối 15° lưu `angle` và vẽ không lỗi; controller cắt ảnh lấy màu cho khối nghiêng nằm trong ảnh. FAIL → implement → PASS. Commit `feat(windows): tilted text drawn tilted`.

### Task 3: Android — ML Kit góc + vẽ nghiêng

**Files:** Modify `engine/AppEngine.kt` (`MlKitOcr` dùng `line.angle` + `cornerPoints` → `Deskew`), `live/LiveLayer.kt`, `ui/Results.kt` (`FullScreenLayer`), `live/LiveController.kt` (ô ⤢ ở góc thật đã xoay, cắt ảnh theo `bounds`), app-core `Layout` (vị trí ô ⤢ đã xoay, kẹp trong màn hình); Test app-core `LayoutTest`

- [ ] **Step 1:** Test JVM: góc dưới-phải của khung 300×60 xoay 20° quanh (0,0) và kẹp vào màn hình. FAIL → implement → PASS; glue; CI xanh. Commit `feat(android): tilted text drawn tilted`.

### Task 4: Windows — cửa sổ cài đặt

**Files:** Create `windows/app/gui/settings_dialog.py`; Modify `windows/app/main.py` (tray "Cài đặt…"), `windows/app/config.py` (`overlay.text_scale`), `windows/app/gui/live_overlay.py` (nhân cỡ chữ); Test `windows/tests/test_settings_dialog.py`, `test_app.py`

- Cửa sổ: kiểu bản dịch (theo game đang chơi), cỡ chữ (80–150%), bản dịch dài (kéo dài / thu nhỏ), model (vinai / opus), phím tắt (chỉ xem). Lưu vào `data_dir/settings.json` (đè lên `config.yaml`), áp dụng ngay (Live khởi động lại).
- [ ] **Step 1:** Test: đổi cỡ chữ → overlay nhân đúng; lưu / đọc lại; đổi model → `switch_model`. FAIL → implement → PASS. Commit `feat(windows): settings window`.

### Task 5: Lỗi nhỏ còn lại từ Phase 4b

- M1 đọc hồ sơ: `UnicodeDecodeError` / `os.replace` lỗi → `.bad`, không crash. M2 file thuật ngữ hỏng → đổi tên `.bad` rồi tạo mới (không ghi đè mất). M3 `set_game` lỗi → không đánh dấu đã áp dụng. M4 kéo cửa sổ khi Live → chờ khung đứng yên 300 ms mới OCR. M5 cache hwnd của game (kiểm `IsWindow`). M7 bản dịch cũ không ghi đè bản vừa sửa. M8 khối giữ nguyên nhưng dời chỗ → vẽ lại đúng chỗ.
- [ ] **Step 1:** Mỗi lỗi một test tái hiện → FAIL → sửa → PASS. Commit `fix: phase 4b minor issues`.

### Task 6: Nghiệm thu

- [ ] **Step 1 — cùng người dùng:** bảng nhiệm vụ nghiêng → bản dịch nghiêng đúng góc, đọc được; chữ thẳng không đổi; cài đặt Windows. Merge vào `main`, push.
