# Phase 4b — Live đè lên chữ gốc + realtime từng câu, hồ sơ game, sửa bản dịch, release v0.1.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live có hai phạm vi **Toàn màn hình** và **Vùng**, bản dịch **đè lên đúng chỗ chữ gốc** và hiện **từng câu ngay khi câu đó hiện xong** (cả Windows lẫn Android, Android không nháy nhờ chụp "Một ứng dụng"); mỗi game có **hồ sơ riêng**; người dùng **sửa bản dịch** (lần sau dùng luôn + `corrections.jsonl`); phát hành **v0.1.0**.

**Architecture:** Logic dùng chung viết bằng Python (chuẩn) rồi port Kotlin, cùng pass fixtures: máy trạng thái Live thêm **OCR giữa chừng** khi chữ đang chạy, **cổng câu** (`SentenceGate`) quyết định câu nào đã xong, `BlockTracker` nhận ra **khối đang dài thêm**; hồ sơ game là JSON theo schema chung. Hai nền tảng dùng **một kiểu overlay** (lớp đè từng khối, click-through) cho cả hai phạm vi. Android dò một lần mỗi phiên ghi màn hình xem overlay có lọt vào ảnh chụp không (`CaptureProbe`) — không lọt (chụp "Một ứng dụng") thì không ẩn overlay khi chụp.

**Tech Stack:** Python 3.11 + PySide6 + ctypes Win32, Kotlin + MediaProjection + `UsageStatsManager`, pytest / JUnit 5, CI + `release.yml` có sẵn.

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md) §5.5, **§5.6c** (Live đè lên + realtime từng câu, thay §5.6/5.6b), §5.8; [AGENT.md](../../../AGENT.md) §9, §10, §11, §12, Phase 4.

## Global Constraints

- **Live — phạm vi:** `screen` (màn hình chứa cửa sổ game / màn hình điện thoại) | `region` (một hoặc nhiều vùng). Cả hai: bản dịch **đè lên đúng khối chữ gốc**, click-through, overlay không lọt vào ảnh chụp. Bỏ thẻ cạnh vùng (`LiveOverlay` / `LiveCard` của 4a) và chế độ `dialogue`/`area`.
- **Nhịp:** `interval_ms=300`, `active_interval_ms=100`, `settle_ms=250`, `max_wait_ms=2000`, `change_threshold=5`, **`partial_interval_ms=500`** (OCR giữa chừng khi chữ đang chạy, chỉ phạm vi `region`), `area_min_interval_ms=1000` (mọi OCR của phạm vi `screen`, kể cả giữa chừng), `area_max_blocks=30`.
- **Câu xong** (`SentenceGate`): câu được theo sau bởi câu khác trong cùng khối; **hoặc** câu cuối kết thúc bằng `.` `!` `?` `…` (có thể kèm `"` `'` `)` `」`) **và** giống hệt ở hai lần OCR liên tiếp; **hoặc** chữ đã dừng hẳn (OCR do ổn định / `max_wait`) → mọi câu còn lại xong. Câu đã hiện không đổi nữa, trừ khi OCR đọc lại khác (→ dịch lại câu đó). Không dịch nháp câu dở.
- **Khối đang dài thêm:** khối mới khớp khối đang hiện khi **góc trên-trái** cách nhau ≤ `near_px` (24) **và** text cũ (chuẩn hóa) là **tiền tố** của text mới → `grown` (giữ key); text giống hệt → `kept`.
- **Android chụp:** mỗi phiên ghi màn hình chạy `CaptureProbe` một lần (ô hồng 24 dp ở góc trên-phải, ~0,3 s) khi bật Live lần đầu; `OVERLAY_HIDDEN` → không ẩn overlay khi chụp; `OVERLAY_CAPTURED` → ẩn overlay khi chụp (nháy nhẹ) và gợi ý một lần "chọn **Một ứng dụng** khi cấp quyền để hết nháy"; `BLACK` → Live tạm dừng ("Mở game đã chọn"). Màn hình bắt đầu app hướng dẫn chọn "Một ứng dụng → game".
- **Hồ sơ game:** định danh Windows = tên exe (chữ thường), Android = package name; `live.scope` (`screen` | `region`, mặc định `region`), `regions` / `ignore_regions` tương đối 0–1 `[x, y, w, h]` theo **vùng client cửa sổ game** (Windows) / **màn hình** (Android); `interval_ms`, `settle_ms`, `change_threshold`; `glossary`; `overrides`. Thiếu trường → mặc định trên. Chưa có hồ sơ → tạo khi người dùng chọn vùng / bật Live lần đầu trong game đó; không nhận được game → `_default`.
- Dữ liệu 4a chuyển sang hồ sơ `_default` lần chạy đầu (Windows `live_regions.json`, `live_mode.txt`; Android `Prefs.regions`, `Prefs.liveMode`) — `dialogue`/`area` đều thành `scope: region`.
- Thứ tự khi dịch: **`overrides` → cache → thuật ngữ + model**. Khóa cache: câu chuẩn hóa + `"{model_id}@{model_version}#{glossary_digest}"` (digest 12 hex, không gồm mục `keep` tự động).
- `corrections.jsonl`: `{"ts", "game", "model", "source", "machine", "corrected"}`; tắt bằng `logging.save_corrections` (mặc định bật).
- Sửa bản dịch Live: phím `ctrl+alt+e` (Windows) / mục menu "Sửa bản dịch gần nhất" (Android); overlay Live vẫn click-through.
- Release `v0.1.0`: tag trên `main` → `release.yml`; **chỉ đẩy tag khi người dùng xác nhận**.
- Nhánh `phase-4b` từ `main`; xong merge vào `main`, push (không PR). Commit kết thúc `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Câu cuối có dấu chấm nhưng chữ vẫn chạy tiếp** (`"Wait." … "Wait. Don't go."`; `"Mr."`, `"..."`) → không hiện câu sai rồi đổi liên tục; câu chỉ coi là xong khi giống hệt hai lần OCR hoặc có câu sau. Fixtures ở Task 1.
2. **Khối dài thêm bị nhận là khối mới** (text dài ra làm tâm hộp dịch chuyển, xuống dòng mới) → giữ key, không vẽ chồng hai bản dịch. Fixture `grown_wraps_to_new_line` ở Task 1.
3. **Live toàn màn hình trên game động liên tục** → ≤ 1 OCR/giây, khối không đổi không dịch lại, overlay không nhấp nháy. Test ở Task 2/3.
4. **Android: người dùng chọn "Toàn màn hình" khi cấp quyền, hoặc chuyển sang app khác khi đang chụp "Một ứng dụng"** → không OCR bản dịch của chính app (ẩn khi chụp), ảnh đen → tạm dừng và báo, không crash. Test ở Task 3.
5. **Cửa sổ game dời / đổi kích thước / thu nhỏ, chuyển sang game khác khi Live đang chạy (Windows)** → vùng đi theo cửa sổ; thu nhỏ → tạm dừng; game khác → hồ sơ + thuật ngữ game đó. Test ở Task 5.

---

### Task 1: Live realtime từng câu — logic dùng chung (Python + Kotlin)

**Files:** Create `shared/fixtures/live_sentences/{README.md, *.json}`, `windows/app/live/sentences.py`; Modify `windows/app/live/machine.py`, `windows/app/live/blocks.py`, `shared/fixtures/live/README.md` (+ fixtures mới), `shared/fixtures/live_blocks/README.md` (+ fixtures mới), `android/app-core/.../live/LiveMachine.kt`, Create `android/app-core/.../live/SentenceGate.kt`; Test `windows/tests/test_live_machine.py`, `windows/tests/test_live_blocks.py`, `windows/tests/test_live_sentences.py`, `android/app-core/src/test/.../live/LiveFixturesTest.kt`

**Interfaces:**
- `LiveParams.partial_interval_ms = 500`; `Action.PARTIAL` — `on_frame` trả `PARTIAL` khi đang ĐANG ĐỔI và đã ≥ `partial_interval_ms` kể từ lúc bắt đầu đổi / lần `PARTIAL` trước (không đổi trạng thái); `OCR` như cũ khi ổn định / `max_wait`. `partial_interval_ms=0` → không bao giờ `PARTIAL`.
- `SentenceGate.done(sentences: list[str], previous: list[str] | None, final: bool) -> int` — số câu đầu đã xong theo luật ở Global Constraints (`previous` = danh sách câu của khối đó ở lần OCR trước).
- `BlockDiff(added, kept, grown, removed)`; `Block` giữ `sentences_done: int` và `shown: list[str]` (bản dịch đã hiện theo câu); `BlockTracker.forget(keys)` (từ 4a review).
- Kotlin: `LiveAction.PARTIAL`, `SentenceGate.done(...)`, `BlockDiff.grown` — cùng fixtures.
- [ ] **Step 1:** Fixtures: `live/typewriter_partial.json` (PARTIAL lúc 600, 1100 ms… rồi OCR khi yên), `live_blocks/grown_same_line.json`, `grown_wraps_to_new_line.json`, `shrunk_is_new.json`; `live_sentences/{two_sentences_typing, last_sentence_needs_two_reads, abbreviation_mr, ellipsis_then_more, quote_after_period, final_flushes_all, ocr_misread_changes_done_sentence}.json`.
- [ ] **Step 2:** Test Python cả ba bộ fixtures + fixtures 4a vẫn pass. FAIL → implement → PASS. Commit `feat(live): partial ocr, sentence gate, growing blocks`.
- [ ] **Step 3:** Port Kotlin, cùng fixtures. FAIL → implement → PASS (`./gradlew :app-core:test`). Commit `feat(live): kotlin port of sentence gate`.

### Task 2: Windows — Live đè lên (toàn màn hình / vùng) + realtime từng câu

**Files:** Modify `windows/app/live/controller.py`, `windows/app/gui/live_overlay.py` (bỏ `LiveOverlay`, `place_above`; `AreaOverlay` thành overlay duy nhất, thêm `set_block(key, text_lines, box, origin)`), `windows/app/gui/worker.py`, `windows/app/main.py` (tray "Live: Toàn màn hình / Vùng" thay "Chế độ Live"); Test `windows/tests/test_live_controller.py`, `windows/tests/test_app.py`, `windows/tests/test_live_parts.py`

**Interfaces:**
- `LiveController(..., scope: "screen" | "region")`: `screen` → một "vùng" = màn hình chứa con trỏ khi bật Live (4b Task 5 đổi thành màn hình của cửa sổ game); `region` → các vùng đã chọn. Mỗi vùng: một job `live_ocr`; kết quả theo khối → `BlockTracker` → mỗi khối `added`/`grown`: `SentenceGate` → gửi `live_translate` **chỉ các câu mới xong**; overlay vẽ cho mỗi khối các câu đã dịch (câu chưa xong không vẽ); khối `removed` → gỡ.
- `PARTIAL` → job `live_ocr` như `OCR` nhưng `final=False` cho `SentenceGate`. Phạm vi `screen`: mọi OCR qua `RateLimiter(area_min_interval_ms)`.
- Job ids, một khe Live trong worker, rollback khi job hỏng giữ như 4a.
- [ ] **Step 1:** Test (chụp giả trả chuỗi ảnh + OCR giả trả chuỗi text): chữ chạy `"Where are"` → `"Where are you going? The"` → `"…? The station is closed today."` → câu 1 được gửi dịch sau OCR giữa chừng thứ 2 (trước khi chữ dừng), câu 2 sau khi yên; overlay khối không bị vẽ lại câu 1; toàn màn hình đổi liên tục 4 s → ≤ 5 OCR; khối giữ nguyên → không job dịch; tắt Live giữa job → overlay đóng, kết quả muộn bị bỏ. FAIL → implement → PASS.
- [ ] **Step 2:** Đo CPU nhàn rỗi 60 s ở phạm vi `screen` (màn hình đứng yên) → < 2%. Commit `feat(windows): live overlays on top, sentence by sentence`.

### Task 3: Android — Live đè lên + realtime từng câu + chụp "Một ứng dụng"

**Files:** Modify `android/app-core/.../live/LiveSession.kt` (khối, câu, phạm vi), `android/app/.../live/LiveController.kt`, `android/app/.../live/LiveLayer.kt` (bỏ `LiveCard`), `Controller.kt` (menu "Live: Toàn màn hình / Vùng", gỡ "Kiểm tra chụp màn hình" khỏi menu chính → giữ trong màn hình app), `MainActivity.kt` (hướng dẫn chọn "Một ứng dụng"), `ui/Prefs.kt` (`liveScope`); Test `android/app-core/src/test/.../live/LiveSessionTest.kt`

**Interfaces:**
- `LiveSession(params, scope, host)` — cùng hành vi Task 2 (port), `LiveHost.setBlock(key, lines: List<String>, box)` / `removeBlock(key)`; `requestOcr(final: Boolean)`.
- `LiveController.captureMode`: `UNKNOWN` → chạy `CaptureProbe` (ô 24 dp góc trên-phải) lần bật Live đầu tiên của phiên ghi màn hình → `HIDDEN` (không ẩn layer khi chụp, không `overlayChanged`) | `CAPTURED` (ẩn khi chụp như 4a, báo gợi ý một lần) | `BLACK` (tạm dừng, báo "Mở game đã chọn rồi bật lại Live").
- Khung đen giữa chừng (người dùng rời game khi chụp "Một ứng dụng") → bỏ tick, không OCR; quay lại game → chạy tiếp.
- [ ] **Step 1:** Test JVM `LiveSession`: kịch bản chữ chạy của Task 2 cho kết quả giống hệt; phạm vi `screen` ≤ 1 OCR/s; `HIDDEN` thì vẽ khối không gọi `overlayChanged`. FAIL → implement → PASS.
- [ ] **Step 2:** Glue + CI `build-android` xanh. Commit `feat(android): live overlays on top, sentence by sentence, single-app capture`.
- [ ] **Step 3 — cùng người dùng:** cài APK nightly, chụp "Một ứng dụng → Reverse: 1999", bật Live vùng + toàn màn hình: không nháy, câu hiện dần theo chữ.

### Task 4: Hồ sơ game — schema, fixtures, Python + Kotlin; bản sửa + khóa cache

**Files:** Create `shared/schemas/profile.schema.json`, `shared/fixtures/profiles/{README.md, full.json, minimal.json, broken_regions.json, broken_json.txt, legacy_4a.json}`, `windows/app/profiles.py`, `windows/app/live/mask.py`, `android/app-core/.../profile/Profile.kt`; Modify `windows/app/live/thumb.py`, `android/app-core/.../live/Thumb.kt`, `windows/app/pipeline.py`, `windows/app/glossary.py`, `windows/app/datalog.py`, `windows/app/config.py`, `windows/app/factory.py`, `android/text-core/.../{Pipeline.kt, Glossary.kt}`; Test `windows/tests/{test_profiles.py, test_pipeline.py, test_glossary.py}`, `android/app-core/src/test/.../profile/ProfileFixturesTest.kt`, `android/text-core/src/test/.../PipelineTest.kt`

**Interfaces:**
- `Profile(id, name, scope="region", regions: list[Rel], ignore: list[Rel], interval_ms=300, settle_ms=250, change_threshold=5.0, glossary: str | None, overrides: dict[str, str])`, `Rel = tuple[float, float, float, float]`; `from_json` (thiếu → mặc định, vùng `w<=0`/`h<=0` bỏ, kẹp 0–1, `scope` lạ → `region`, key `overrides` chuẩn hóa khoảng trắng), `to_json`.
- `ProfileStore(dir)`: `get`, `get_or_default(game_id, name)`, `save` (ghi tạm rồi đổi tên), file hỏng → `<id>.json.bad` + `None`; `migrate_phase4a(data_dir)`. `to_px(rel, frame)`, `to_rel(px, frame)`.
- `mask.ignore_mask(...)`; `thumb.diff(a, b, mask=None)` (mask che hết → `0.0`). Kotlin tương ứng.
- `Glossary.digest()`, `Glossary.add_entry(source, target | None)`; `Pipeline(..., model_version="0", overrides=None)`, `Pipeline.cache_ns`, `Pipeline.set_game(game, glossary, overrides)`, `Pipeline.correct(source, machine, corrected)`; `CorrectionLogger(path, enabled)`; config `logging.save_corrections`. Kotlin: `digest()`, `Pipeline(modelVersion, overrides)`, `setGame`.
- [ ] **Step 1:** Test hồ sơ: fixtures (Python + Kotlin), round-trip, `.bad`, migrate 4a, `to_px`/`to_rel` (cửa sổ `(100, 50, 1280, 720)`), mask nửa ảnh / che hết. FAIL → implement → PASS. Commit `feat(profiles): per-game profile schema, python + kotlin`.
- [ ] **Step 2:** Test bản sửa: override → không gọi translator / cache; khớp dù khác khoảng trắng; `correct()` dùng ngay lần sau; thêm `map` → namespace cache đổi; `add_keep` tự động không đổi digest; `corrections.jsonl` 6 trường; tắt thì không ghi. FAIL → implement → PASS. Commit `feat(pipeline): user overrides, versioned cache key, corrections log`.

### Task 5: Windows — nhận game, Live theo hồ sơ, sửa bản dịch

**Files:** Create `windows/app/gui/foreground.py`, `windows/app/gui/correct_dialog.py`; Modify `windows/app/main.py`, `windows/app/live/controller.py`, `windows/app/gui/worker.py` (jobs `set_game`, `correct`), `windows/app/gui/overlay.py` (nút "Sửa"), `windows/app/gui/selector.py` (chọn nhiều vùng: kéo nhiều lần, Enter xong, Esc hủy; phím `I` đổi sang vẽ vùng bỏ qua), `windows/app/config.py` (`hotkeys.edit_last`); Test `windows/tests/{test_foreground.py, test_correct_dialog.py, test_live_controller.py, test_app.py}`

**Interfaces:**
- `foreground.current_game() -> GameWindow | None` (`exe`, `title`, `client` vật lý, `minimized`; bỏ qua cửa sổ của app), `game_window(exe)`.
- Live mỗi tick lấy lại `client` → quy vùng tương đối ra pixel; phạm vi `screen` = màn hình chứa cửa sổ game; thu nhỏ / mất cửa sổ → bỏ tick, báo 1 lần; vùng ngoài mọi màn hình → báo 1 lần (4a M3); `ignore` → mask.
- Đổi foreground sang exe khác có hồ sơ khi Live bật → `start` lại + job `set_game`. Tray "Game: <tên>".
- `CorrectDialog(segments)` → `Correction(source, machine, corrected)` (chỉ câu đã đổi) + `terms` (`nguồn = đích`, đích trống → `keep`); job `correct` ghi override vào hồ sơ + thuật ngữ vào `data_dir/glossary/games/<id>.json`; `Ctrl+Alt+E` sửa kết quả gần nhất (Live hoặc một lần), chưa có → báo "Chưa có bản dịch nào để sửa".
- [ ] **Step 1:** Test: cửa sổ dời `(100,50)→(400,300)` → ảnh chụp đúng chỗ mới; thu nhỏ → 0 job, báo 1 lần; `ignore` phủ hết → 0 job khi nhấp nháy; chuyển sang game B → `set_game`, overlay game A đóng; chọn 2 vùng + 1 vùng bỏ qua → hồ sơ lưu đủ; dialog chỉ trả câu đã đổi; `Arcanist =` → `keep`; sửa → override + `corrections.jsonl` + overlay cập nhật. FAIL → implement → PASS.
- [ ] **Step 2:** Commit `feat(windows): game profiles and corrections`.

### Task 6: Android — nhận game, hồ sơ, sửa bản dịch

**Files:** Create `android/app/.../profile/{GameDetector.kt, ProfileRepo.kt}`, `android/app/.../ui/CorrectView.kt`, app-core `profile/ProfileLogic.kt`; Modify `Controller.kt`, `live/LiveController.kt`, `ui/RegionEditView.kt` (nút "Vùng bỏ qua"), `ui/Results.kt` (nút "Sửa"), `MainActivity.kt` (cấp Usage Access), `AndroidManifest.xml` (`PACKAGE_USAGE_STATS`), `engine/AppEngine.kt` (thuật ngữ + overrides theo game), app-core `TranslationEngine.kt` (job sửa); Test `android/app-core/src/test/.../profile/ProfileLogicTest.kt`, `TranslationEngineTest.kt`

**Interfaces:**
- `ProfileLogic.pickGame(foreground: String?, manual: String?, own: String) -> String` (thủ công > foreground; app mình / null → `_default`), `migratePrefs(regions, liveMode) -> Profile`.
- `GameDetector.current(): String?` (`UsageStatsManager.queryEvents` 10 s gần nhất, `ACTIVITY_RESUMED` cuối; thiếu quyền → `null`). Khi chụp "Một ứng dụng", game đã chọn lúc cấp quyền là game hiện tại nếu không đọc được Usage Access.
- `ProfileRepo` (filesDir/profiles/<package>.json). Menu: "Game: <tên> ▸" (chọn tay / "Tự nhận"), "Sửa bản dịch gần nhất". `CorrectView` overlay focusable (ô sửa mỗi câu + ô thuật ngữ) → job sửa trên luồng engine → hồ sơ + `corrections.jsonl`.
- Live FLAG_SECURE (4a M7): khung đen + OCR rỗng → báo một lần.
- [ ] **Step 1:** Test JVM `ProfileLogic` + job sửa ghi override và dùng ngay ở job sau. FAIL → implement → PASS.
- [ ] **Step 2:** Glue; CI xanh. Commit `feat(android): game profiles and corrections`.

### Task 7: Nghiệm thu, FPS, tài liệu, release v0.1.0

**Files:** Create `CHANGELOG.md`; Modify `AGENT.md`, `README.md`, `windows/app/__init__.py` (`__version__ = "0.1.0"`), `.github/workflows/release.yml` (ghi chú phát hành từ `CHANGELOG.md`)

- [ ] **Step 1 — cùng người dùng** (Reverse: 1999, Windows + Android):
  - [ ] Live vùng và toàn màn hình: bản dịch đè đúng chỗ, câu hiện dần theo chữ chạy, câu đã hiện không nhảy; Android không nháy (chụp "Một ứng dụng").
  - [ ] Hồ sơ tự tạo; mở lại app → tự nhận game; dời / phóng to cửa sổ game (Windows) → vẫn đúng vùng.
  - [ ] Sửa một câu → lần sau hiện bản sửa; thêm thuật ngữ → câu sau dùng đúng.
  - [ ] **FPS**: tắt Live / Live đứng yên / Live khi thoại chạy (Windows: Xbox Game Bar; Android: "Hiển thị tốc độ khung hình" trong tùy chọn nhà phát triển) → giảm ≤ 5%.
- [ ] **Step 2:** Ghi số đo vào AGENT.md, cập nhật README + CHANGELOG; chạy toàn bộ test; merge `phase-4b` vào `main`, push.
- [ ] **Step 3 — người dùng xác nhận trước:** `git tag v0.1.0 && git push origin v0.1.0` → workflow `release` xanh → release `v0.1.0` có `ScreenTrans-windows.zip` + `ScreenTrans-android.apk`.
