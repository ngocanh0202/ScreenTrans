# Phase 4a — Live (tự dịch khi chữ đổi) trên Windows + Android — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bật Live một lần, app **tự dịch mỗi khi chữ trong vùng đổi** (chờ chữ hiện xong), hiện bản dịch cạnh vùng không chặn chuột/chạm; chế độ **Live vùng lớn** cho game thoại bong bóng (chỉ dịch khối mới, ≤ 1 OCR/giây) — trên cả Windows và Android.

**Architecture:** Logic Live là **máy trạng thái thuần** (`LiveMachine`) và **bộ theo dõi khối** (`BlockTracker`), viết bằng Python (chuẩn) rồi port Kotlin, cùng pass bộ fixtures `shared/fixtures/live/*.json` (giống cách làm hậu xử lý). Mỗi nền tảng chỉ lo: chụp ảnh thu nhỏ của vùng theo nhịp, tính độ sai khác, gọi máy trạng thái, gửi job OCR+dịch cho worker/engine có sẵn (job mới thay job cũ), và vẽ overlay Live click-through. Bản dịch hiện **từng câu** ngay khi dịch xong.

**Tech Stack:** Python 3.11 + PySide6 (Windows), Kotlin + coroutines (Android, module `app-core` JVM-testable), pytest, JUnit 5, CI hiện có.

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md) §5.6, §5.6b; [AGENT.md](../../../AGENT.md) §11, §13, Phase 4.

## Global Constraints

- Tham số mặc định (AGENT.md §11–12): `interval_ms=300`, `active_interval_ms=100`, `settle_ms=250`, `max_wait_ms=2000`, `change_threshold=5`, `area_min_interval_ms=1000`, `area_max_blocks=30`.
- Độ sai khác ảnh: ảnh **xám** (`0.299R+0.587G+0.114B`), thu về **rộng 64 px** (giữ tỉ lệ), **trung bình |Δ|** từng điểm (0–255) so với **ảnh thu nhỏ ngay trước**. Định nghĩa này giống nhau ở hai nền tảng (cách lấy mẫu có thể khác chút — ngưỡng 5 chịu được).
- Màn hình đứng yên → **không OCR**; CPU Live nhàn rỗi < 2% (Windows).
- Overlay Live **không chặn chuột/chạm** (Windows `Qt.WindowTransparentForInput` + loại khỏi ảnh chụp; Android `FLAG_NOT_TOUCHABLE`), đặt **cạnh vùng, không che chữ gốc** (Live thoại).
- Android không loại overlay khỏi ảnh chụp được: Live thoại đặt overlay **ngoài** vùng; Live vùng lớn **ẩn overlay khi chụp ảnh OCR**, và **bỏ qua thay đổi do chính overlay gây ra** (sau mỗi lần vẽ lại overlay, khung kế tiếp thành ảnh mốc mới).
- Một job OCR+dịch tại một thời điểm (worker/engine hiện có, job mới thay job chờ).
- Phím tắt Windows: `ctrl+alt+l` bật/tắt Live. Android: mục menu **Bật Live / Tắt Live**.
- Vùng Live: Windows dùng **vùng đã chọn gần nhất** lưu ở `data_dir/live_regions.json` (pixel vật lý); Android dùng **các vùng đã lưu** (Phase 3). Hồ sơ theo game để Phase 4b.
- Chế độ Live (`dialogue` | `area`) chọn trong tray (Windows) / menu (Android), nhớ giữa các lần chạy.
- Nhánh `phase-4a` từ `main`; xong thì merge vào `main` và push (không PR). Commit kết thúc `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Chữ hiện dần (typewriter) dài hơn `max_wait_ms`** → vẫn dịch bản hoàn chỉnh cuối cùng, không dừng ở nửa câu. Fixture `typewriter_long` ở Task 1.
2. **Mũi tên ▼ nhấp nháy / nền động nhẹ** → không OCR lặp lại (thay đổi dưới ngưỡng; text không đổi → không dịch lại). Fixtures `blinking_arrow`, `same_text_new_frame` ở Task 1.
3. **Overlay Live vùng lớn trên Android tự kích hoạt vòng lặp OCR** (vẽ bản dịch → ảnh đổi → OCR lại) → không xảy ra. Test `self_change_is_ignored` ở Task 1/2.
4. **Tắt Live / đổi vùng / thoát app giữa chừng một job** → overlay Live gỡ sạch, job cũ không vẽ lại. Test ở Task 4 và Task 6.
5. **Đổi game/cửa sổ khi Live đang chạy (Windows)** → Live vẫn chụp đúng vùng màn hình, không crash khi vùng nằm ngoài màn hình (rút màn hình phụ). Test ở Task 4.

---

### Task 1: Đặc tả Live bằng fixtures + máy trạng thái Python

**Files:** Create `shared/fixtures/live/README.md`, `shared/fixtures/live/*.json` (≥ 8), `windows/app/live/__init__.py`, `windows/app/live/machine.py`; Test `windows/tests/test_live_machine.py`

**Interfaces:**
- Produces:
  - `@dataclass LiveParams(interval_ms=300, active_interval_ms=100, settle_ms=250, max_wait_ms=2000, change_threshold=5.0)`.
  - `class Action(Enum): WAIT, OCR` — và `next_delay_ms(machine) -> int` cho nhịp chụp kế tiếp (300 khi IDLE, 100 khi CHANGING).
  - `class LiveMachine(params)`: `on_frame(now_ms: int, diff: float) -> Action` (diff = sai khác so với ảnh ngay trước); `on_text(now_ms: int, text: str) -> Literal["translate","skip","wait"]` (gọi sau OCR); `on_overlay_changed()` (khung kế tiếp không tính là thay đổi); thuộc tính `state: Literal["idle","changing"]`.
  - Quy tắc (AGENT.md §11): IDLE + diff > ngưỡng → CHANGING (ghi `changed_at`, `last_change`); CHANGING: diff > ngưỡng → cập nhật `last_change`; `now - last_change >= settle_ms` **hoặc** `now - changed_at >= max_wait_ms` → `OCR` và về trạng thái "đã OCR". `on_text`: text chuẩn hóa rỗng → `skip`; giống text đã dịch gần nhất → `skip`; text mới **bắt đầu bằng** text OCR lần trước, dài hơn, **và** lần OCR này là do `max_wait` (chữ vẫn chạy) → `wait` (quay lại CHANGING); còn lại → `translate` (ghi nhớ text).
  - Fixture JSON: `{"name", "params": {...tùy chọn...}, "events": [{"t": int, "diff": float} | {"t": int, "ocr_text": str} | {"t": int, "overlay_changed": true}], "expected": [{"t": int, "action": "ocr" | "translate" | "skip" | "wait"}]}` — `expected` liệt kê **mọi** hành động khác `WAIT` theo thứ tự.
- [ ] **Step 1:** Viết fixtures: `typewriter_settles` (diff 20 mỗi 100 ms trong 900 ms rồi 0 → `ocr` tại `last_change+250`, text → `translate`), `skip_instant` (1 bước nhảy → ocr sau 250 ms), `blinking_arrow` (diff 3 xen kẽ → không có hành động), `noisy_background_max_wait` (diff 30 liên tục → `ocr` tại 2000 ms), `typewriter_long` (chạy 3 s: ocr ở 2000 ms với text cụt → `wait`, ocr lần 2 khi yên → text đủ → `translate`), `same_text_new_frame` (ảnh đổi nhưng OCR ra text giống bản đã dịch → `skip`), `empty_text` (→ `skip`), `self_change_is_ignored` (`overlay_changed` rồi diff 40 một khung → không có hành động).
- [ ] **Step 2:** Test tham số hóa đọc mọi fixture → so danh sách hành động. FAIL → implement `machine.py` → PASS.
- [ ] **Step 3:** Commit `feat(live): shared live state machine spec and python reference`.

### Task 2: Theo dõi khối (Live vùng lớn) — Python

**Files:** Create `windows/app/live/blocks.py`, `shared/fixtures/live_blocks/*.json` (≥ 4); Test `windows/tests/test_live_blocks.py`

**Interfaces:**
- Produces: `@dataclass Block(key: str, text: str, box: tuple[float,float,float,float])`; `class BlockTracker(max_blocks=30, near_px=24)`: `update(paragraphs: list[Paragraph]) -> BlockDiff` với `BlockDiff(added: list[Block], kept: list[Block], removed: list[Block])` — khối **giữ nguyên** khi text chuẩn hóa giống **và** tâm cách ≤ `near_px`; quá `max_blocks` → giữ các khối trên→dưới đầu tiên; `key` ổn định cho khối giữ nguyên. `class RateLimiter(min_interval_ms=1000)`: `allow(now_ms) -> bool`.
- [ ] **Step 1:** Fixtures: bong bóng mới xuất hiện (added 1, kept cũ), bong bóng cũ biến mất (removed), bong bóng dịch nhẹ 10 px (kept), cùng chữ ở chỗ khác xa (removed + added), 40 khối (giữ 30). Test + `RateLimiter` (0 → True, 500 → False, 1000 → True). FAIL → implement → PASS.
- [ ] **Step 2:** Commit `feat(live): block tracker for large-area live`.

### Task 3: Port Kotlin (app-core) cùng fixtures

**Files:** Create `android/app-core/src/main/kotlin/dev/screentrans/core/live/{LiveMachine.kt, BlockTracker.kt}`; Test `.../live/LiveFixturesTest.kt` (đọc `shared/fixtures/live*`); Modify `android/app-core/build.gradle.kts` (system property `shared.dir` như text-core)
- **Interfaces:** cùng tên/hành vi Task 1–2 (`LiveMachine.onFrame/onText/onOverlayChanged`, `BlockTracker.update`, `RateLimiter.allow`). Không dùng cờ regex inline (ICU).
- [ ] **Step 1:** Test fixtures (dynamic tests) → FAIL → port → PASS. **Step 2:** Commit `feat(android): live state machine and block tracker`.

### Task 4: Live trên Windows

**Files:** Create `windows/app/live/controller.py`, `windows/app/gui/live_overlay.py`, `windows/app/live/regions.py`; Modify `windows/app/main.py` (phím `toggle_live`, tray "Live: Bật/Tắt", "Chế độ Live ▸ Khung thoại / Vùng lớn", "Chọn lại vùng Live"), `windows/app/gui/worker.py` (job mode `"live"`: OCR các vùng rồi `Pipeline.iter_sentences`, phát tín hiệu `segment`-list sau mỗi câu), `windows/app/pipeline.py`; Test `windows/tests/test_live_controller.py`, `windows/tests/test_pipeline.py`

**Interfaces:**
- `Pipeline.iter_sentences(paragraphs) -> Iterator[list[Segment]]` — sau **mỗi câu** dịch xong yield **toàn bộ** danh sách segment hiện tại (câu chưa dịch hiển thị `"…"`); dùng cache/thuật ngữ như cũ.
- `regions.py`: `load_live_regions(data_dir) -> list[tuple[int,int,int,int]]`, `save_live_regions(data_dir, regions)` (JSON, pixel vật lý); vùng được chọn bằng `RegionSelector` có sẵn ("Chọn lại vùng Live"; Ctrl+Alt+L khi chưa có vùng → mở chọn vùng trước).
- `LiveController(QObject)`: `start(mode, regions)`, `stop()`, signal `submit(Job)`; `QTimer` theo `next_delay_ms`; mỗi tick chụp **chỉ các vùng** (`capture_region`), ảnh thu nhỏ → diff → `LiveMachine.on_frame`; `OCR` → gửi `Job(mode="live", regions=...)`; kết quả → `on_text` (text ghép các vùng) → nếu `translate` thì worker dịch dần, overlay cập nhật từng câu; vùng nằm ngoài màn hình (rút màn hình phụ) → bỏ qua vùng đó, báo tray một lần.
- Vùng lớn: tick 1 lần/`area_min_interval_ms` khi đang đổi; `BlockTracker` → overlay đè từng khối (giống `FullscreenOverlay` nhưng `Qt.WindowTransparentForInput`, không chip "Đang dịch…").
- `LiveOverlay(QWidget)`: frameless, on-top, `Qt.WindowTransparentForInput`, `exclude_from_capture`; đặt **ngay trên** vùng (spec §5.6: mặc định phía trên, tràn thì dưới); nút nhỏ ẩn/hiện không cần (tắt bằng Ctrl+Alt+L).
- [ ] **Step 1:** Test (pytest-qt, chụp giả trả chuỗi ảnh định sẵn, worker giả): chữ chạy → 1 job sau khi yên; ảnh đứng yên 3 s → 0 job; tắt Live giữa job → kết quả về sau bị bỏ, overlay đóng; `iter_sentences` yield sau mỗi câu với "…" cho câu chưa dịch; vùng ngoài màn hình → không crash, `notify` 1 lần; Ctrl+Alt+L khi chưa có vùng → mở selector. FAIL → implement → PASS.
- [ ] **Step 2:** Đo CPU khi Live nhàn rỗi 60 s (`psutil.Process().cpu_percent`) trên máy dev → Expected < 2%. Commit `feat(windows): live mode`.

### Task 5: Live trên Android

**Files:** Create `android/app/src/main/kotlin/dev/screentrans/live/{LiveController.kt, LiveLayer.kt}`, `android/app-core/src/main/kotlin/dev/screentrans/core/live/Thumb.kt`; Modify `Controller.kt` (menu "Bật Live"/"Tắt Live", "Live: Khung thoại / Vùng lớn"), `capture/ScreenCapturer.kt` (`thumbnail(rect, width=64): FloatArray?` từ frame đang giữ — không tạo Bitmap toàn màn hình mỗi tick), `ui/Prefs.kt` (`liveMode`); Test `android/app-core/src/test/.../live/ThumbTest.kt`

**Interfaces:**
- `Thumb.diff(a: FloatArray, b: FloatArray): Float` (mean |Δ|, kích thước khác → `Float.MAX_VALUE`); `Thumb.fromArgb(pixels, w, h, targetW=64): FloatArray` (xám + thu nhỏ trung bình khối).
- `LiveController(scope, capturer, engine, overlays, prefs)`: vòng lặp coroutine theo `next_delay_ms`; thoại: overlay `LiveLayer` (FLAG_NOT_TOUCHABLE) đặt **ngoài** vùng; vùng lớn: ẩn layer khi chụp ảnh OCR, `onOverlayChanged()` sau mỗi lần vẽ; dừng khi tắt Live / service dừng / MediaProjection bị thu hồi.
- `TranslationEngine` thêm job progressive: `EngineEvent.Partial(jobId, segments)` sau mỗi câu (dùng `Pipeline.iterSentences` port từ Task 4 — thêm vào `text-core` cùng test).
- [ ] **Step 1:** Test JVM: `Thumb.diff`/`fromArgb` (ảnh giống → 0; ảnh trắng vs đen → 255; nhiễu 1 điểm nhỏ → < ngưỡng 5); `Pipeline.iterSentences` (text-core); engine `Partial` trước `Done`. FAIL → implement → PASS.
- [ ] **Step 2:** Implement Android glue; CI check xanh. Commit `feat(android): live mode`.

### Task 6: Nghiệm thu + tài liệu

**Files:** Modify `AGENT.md` (Phase 4a tick + số đo), `README.md`

- [ ] **Step 1 — cùng người dùng:** Windows (Ctrl+Alt+L) và Android (menu Bật Live) trên Reverse: 1999:
  - [ ] Thoại chữ chạy → bản dịch hiện sau khi chữ dừng (đo: câu đầu ~0,3 s Windows/vinai, ~0,3 s Android/opus); bấm qua thoại nhanh → không kẹt bản cũ.
  - [ ] Đứng yên trên một câu 1 phút → không OCR lại (Windows: CPU < 2%; Android: không nóng máy).
  - [ ] Overlay không chặn chuột/chạm vào game; không che chữ gốc.
  - [ ] Live vùng lớn trên một game có bong bóng (nếu có) → chỉ bong bóng mới được dịch, không nhấp nháy liên tục.
  - [ ] Tắt Live → overlay biến mất ngay.
  - [ ] FPS game trước/sau khi bật Live.
- [ ] **Step 2:** Ghi số đo, cập nhật tài liệu; chạy toàn bộ test; merge `phase-4a` vào `main`, push.
