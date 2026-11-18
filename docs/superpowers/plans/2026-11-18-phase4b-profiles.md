# Phase 4b — Hồ sơ game + sửa bản dịch + release v0.1.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mỗi game có **hồ sơ riêng** (tự nhận game, vùng Live tên/thoại/lựa chọn/vùng lớn, vùng bỏ qua, tham số chờ chữ, thuật ngữ, bản sửa của người dùng), người dùng **sửa bản dịch** ngay trên overlay (lần sau dùng luôn + ghi `corrections.jsonl`), rồi phát hành **v0.1.0** cho Windows + Android.

**Architecture:** Hồ sơ game là **một file JSON / game** theo schema dùng chung `shared/schemas/profile.schema.json`; Python là chuẩn, Kotlin pass cùng fixtures `shared/fixtures/profiles/*.json` (giống postprocess/live). Pipeline hai nền tảng thêm bước **`overrides` → cache → thuật ngữ + model**, và khóa cache gồm **model id + phiên bản model + digest thuật ngữ**. Mỗi nền tảng lo: nhận game đang chạy, quy đổi vùng tương đối (0–1) ra pixel, UI chọn vùng nhiều loại, UI sửa bản dịch.

**Tech Stack:** Python 3.11 + PySide6 + ctypes Win32 (Windows), Kotlin + `UsageStatsManager` (Android), pytest / JUnit 5, CI + workflow `release.yml` có sẵn.

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md) §5.4, §5.5, §5.6, §5.8; [AGENT.md](../../../AGENT.md) §9 (sửa từ overlay), §10 (hồ sơ game), §11, §12, Phase 4.

## Global Constraints

- Hồ sơ: định danh Windows = **tên exe** (chữ thường, vd `reverse1999.exe`), Android = **package name**; `live.mode` ∈ `dialogue` | `area` (mặc định `dialogue`); vùng `dialogue` / `name` / `choices` / `area`, `ignore_regions`; tham số `interval_ms`, `settle_ms`, `change_threshold` (thiếu → mặc định AGENT.md §12: 300 / 250 / 5); `glossary` (tên file trong thư mục thuật ngữ game); `overrides` (câu nguồn **đã chuẩn hóa** → bản dịch người dùng).
- Tọa độ vùng lưu **tương đối 0–1** theo **vùng client của cửa sổ game** (Windows) / **màn hình** (Android); `[x, y, w, h]`, giá trị kẹp trong [0, 1].
- Game chưa có hồ sơ → tạo hồ sơ mặc định **khi người dùng chọn vùng lần đầu** cho game đó. Không nhận được game (desktop, thiếu quyền) → hồ sơ `_default`.
- Thứ tự áp dụng khi dịch: **`overrides` → cache → thuật ngữ + model** (AGENT.md §9).
- Khóa cache: `câu chuẩn hóa` + `"{model_id}@{model_version}#{glossary_digest}"`; `glossary_digest` = 12 ký tự hex đầu của SHA-1 trên các mục **từ file/người dùng** (không gồm mục `keep` tự động trong phiên).
- `corrections.jsonl`: mỗi dòng `{"ts", "game", "model", "source", "machine", "corrected"}`; tắt được bằng `logging.save_corrections` (mặc định bật).
- Overlay Live vẫn click-through; sửa bản dịch Live qua **phím tắt / mục menu "Sửa bản dịch gần nhất"** (không đổi overlay sang tương tác).
- Android: nhận game qua `UsageStatsManager` (quyền Usage Access); thiếu quyền → **chọn game bằng tay** trong menu, không chặn tính năng nào.
- Vùng Live cũ (Phase 4a: `data_dir/live_regions.json`, `live_mode.txt`; Android `Prefs.regions`, `Prefs.liveMode`) được **chuyển vào hồ sơ `_default`** lần chạy đầu, không mất.
- Release `v0.1.0`: tag `v0.1.0` trên `main` → `release.yml` build và đăng exe zip + APK. **Đẩy tag chỉ khi người dùng xác nhận** (thao tác công khai).
- Nhánh `phase-4b` từ `main`; xong merge vào `main` và push (không PR). Commit kết thúc `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Cửa sổ game di chuyển / đổi kích thước / thu nhỏ khi Live đang chạy (Windows)** → vùng Live đi theo cửa sổ; cửa sổ thu nhỏ hoặc đóng → Live tạm dừng, không OCR desktop, không crash. Test ở Task 3.
2. **File hồ sơ hỏng / thiếu trường / phiên bản lạ** → dùng mặc định cho trường thiếu, file hỏng được đổi tên `.bad` và tạo lại, app không crash. Fixtures `broken_*.json` ở Task 1.
3. **Bản sửa của người dùng không bao giờ bị cache / model ghi đè**, kể cả khi câu OCR khác khoảng trắng; sửa xong thấy ngay ở lần OCR kế tiếp. Test ở Task 2.
4. **Chuyển game giữa chừng (alt-tab sang game khác) khi Live đang chạy** → Live dừng ở game cũ, dùng hồ sơ + thuật ngữ game mới; bản dịch game cũ không hiện ở game mới. Test ở Task 3 / Task 5.
5. **`ignore_regions` phủ toàn bộ vùng thoại** → không chia cho 0, không OCR liên tục; chỉ coi như "không có thay đổi". Test ở Task 1 (mask) và Task 3.

---

### Task 1: Hồ sơ game — schema, fixtures, Python + Kotlin

**Files:** Create `shared/schemas/profile.schema.json`, `shared/fixtures/profiles/{README.md, full.json, minimal.json, broken_regions.json, broken_json.txt}`, `windows/app/profiles.py`, `windows/app/live/mask.py`, `android/app-core/src/main/kotlin/dev/screentrans/core/profile/Profile.kt`; Modify `windows/app/live/thumb.py`, `android/app-core/.../live/Thumb.kt`; Test `windows/tests/test_profiles.py`, `android/app-core/src/test/kotlin/dev/screentrans/core/profile/ProfileFixturesTest.kt`

**Interfaces:**
- Python `@dataclass Profile(id: str, name: str, mode: str = "dialogue", regions: dict[str, list[Rel]], ignore: list[Rel], interval_ms=300, settle_ms=250, change_threshold=5.0, glossary: str | None, overrides: dict[str, str])` với `Rel = tuple[float, float, float, float]`; `Profile.from_json(dict) -> Profile` (trường thiếu → mặc định, vùng lỗi bị bỏ, giá trị kẹp 0–1), `Profile.to_json() -> dict`.
- `ProfileStore(dir: Path)`: `get(game_id) -> Profile | None`, `get_or_default(game_id, name) -> Profile` (chưa lưu), `save(profile)` (ghi file tạm rồi đổi tên), file hỏng → đổi tên `<id>.json.bad`, trả `None`; `migrate_phase4a(data_dir)` → tạo `_default` từ `live_regions.json` + `live_mode.txt` (pixel → tương đối theo màn hình chính) rồi đổi tên file cũ `.migrated`.
- `to_px(rel, frame: tuple[x, y, w, h]) -> tuple[int,int,int,int]`, `to_rel(px, frame) -> Rel`.
- `mask.ignore_mask(region_px, ignore_px_list, thumb_w, thumb_h) -> np.ndarray[bool]`; `thumb.diff(a, b, mask=None)` — chỉ tính điểm `mask==True`; mask rỗng (toàn bộ bị bỏ) → `0.0`.
- Kotlin: `Profile` (cùng trường, camelCase), `Profile.parse(json: String): Profile?` (JSON hỏng → null), `serialize()`, `RelRect` dùng lại; `Thumb.diff(a, b, mask: BooleanArray? = null)`.
- [ ] **Step 1:** Fixtures: mỗi file `{"input": <json hồ sơ hoặc chuỗi>, "expected": <hồ sơ sau chuẩn hóa | null>}`; README ghi luật (mặc định, kẹp, bỏ vùng `w<=0`/`h<=0`, `mode` lạ → `dialogue`, key `overrides` được chuẩn hóa khoảng trắng).
- [ ] **Step 2:** Test Python: fixtures; round-trip `to_json`/`from_json`; `ProfileStore` lưu/đọc, file hỏng → `.bad` + `None`; migrate 4a; `to_px`/`to_rel` (cửa sổ ở `(100, 50, 1280, 720)`); `diff` với mask che nửa ảnh chỉ thấy thay đổi ở nửa còn lại; mask che hết → `0.0`. FAIL → implement → PASS.
- [ ] **Step 3:** Test Kotlin cùng fixtures + `Thumb.diff` có mask. FAIL → implement → PASS (`./gradlew :app-core:test`).
- [ ] **Step 4:** Commit `feat(profiles): per-game profile schema, python + kotlin`.

### Task 2: Bản sửa (overrides) + khóa cache + corrections.jsonl

**Files:** Modify `windows/app/pipeline.py`, `windows/app/glossary.py`, `windows/app/datalog.py`, `windows/app/config.py`, `windows/app/factory.py`, `android/text-core/.../Pipeline.kt`, `android/text-core/.../Glossary.kt`; Test `windows/tests/test_pipeline.py`, `windows/tests/test_glossary.py`, `android/text-core/src/test/.../PipelineTest.kt`

**Interfaces:**
- `Glossary.digest() -> str` (12 hex, bỏ qua mục `keep` thêm bởi `add_keep`); `Glossary.add_entry(source, target | None)` (mục người dùng, có tính vào digest).
- `Pipeline(..., model_version: str = "0", overrides: dict[str, str] | None = None)`; `Pipeline.cache_ns` = `f"{model_id}@{model_version}#{glossary.digest()}"` dùng thay `model_id` khi gọi cache; `Pipeline.set_game(game, glossary, overrides)`; `Pipeline.correct(source, machine, corrected) -> None` — ghi `overrides[normalize(source)]`, `CorrectionLogger.log(...)`.
- `CorrectionLogger(path, enabled)` trong `datalog.py`, `logging.save_corrections: bool = True` trong config.
- Kotlin: `Glossary.digest()`, `Pipeline(..., modelVersion: String = "0", overrides: MutableMap<String, String> = mutableMapOf())`, `setGame(...)`, override trước cache.
- [ ] **Step 1:** Test: câu có override → không gọi translator, không đọc cache; override khớp dù OCR khác khoảng trắng; `correct()` rồi dịch lại câu đó → bản sửa; đổi thuật ngữ (thêm `map`) → cache cũ không dùng (namespace đổi); `add_keep` tự động không đổi digest; `corrections.jsonl` đúng 6 trường; `save_corrections=False` → không ghi. Kotlin: override + digest. FAIL → implement → PASS.
- [ ] **Step 2:** Commit `feat(pipeline): user overrides, versioned cache key, corrections log`.

### Task 3: Windows — nhận game, Live theo hồ sơ (nhiều vùng, vùng bỏ qua)

**Files:** Create `windows/app/gui/foreground.py`, `windows/app/gui/region_kinds.py`; Modify `windows/app/main.py`, `windows/app/live/controller.py`, `windows/app/gui/worker.py`, `windows/app/gui/live_overlay.py`, `windows/app/gui/selector.py`; Delete use of `windows/app/live/regions.py` (giữ cho migrate); Test `windows/tests/test_foreground.py`, `windows/tests/test_live_controller.py`, `windows/tests/test_app.py`

**Interfaces:**
- `foreground.current_game() -> GameWindow | None` — `GameWindow(exe: str, title: str, client: tuple[x, y, w, h] physical, minimized: bool)` (Win32: `GetForegroundWindow`, `GetWindowThreadProcessId`, `QueryFullProcessImageNameW`, `GetClientRect` + `ClientToScreen`, `IsIconic`); bỏ qua cửa sổ của chính app; `game_window(exe) -> GameWindow | None` tìm lại cửa sổ theo exe (cho tick).
- `LiveController.start(profile, window_provider)`: mỗi tick lấy lại `client` của cửa sổ → quy đổi vùng tương đối ra pixel; cửa sổ thu nhỏ / mất → bỏ qua tick (không OCR, báo tray 1 lần "Game đã thu nhỏ/đóng — Live tạm dừng"); vùng `ignore` → mask trong `diff`. Vùng theo loại: job `live_ocr` gửi ảnh **theo thứ tự cố định** `dialogue..., name..., choices...` kèm `kinds: list[str]` (sửa luôn lỗi lệch chỉ số khi một vùng chụp lỗi — giữ `None` chỗ trống).
- Hiển thị: một `LiveOverlay` cạnh vùng `dialogue` đầu tiên: `[Tên]` (từ vùng `name`, không dịch) + bản dịch thoại + các lựa chọn (mỗi dòng `▸ …`).
- Chọn vùng: tray "Chọn vùng Live…" → chọn **thoại** (bắt buộc), rồi **tên** và **lựa chọn** (Esc để bỏ qua từng bước, chữ hướng dẫn trên lớp chọn); chế độ Vùng lớn → một vùng `area` + tùy chọn vùng bỏ qua. Lưu vào hồ sơ game đang ở foreground (tạo mới nếu chưa có, `name` = tiêu đề cửa sổ).
- Đổi game: tray hiện "Game: <tên>"; khi cửa sổ foreground đổi sang exe khác có hồ sơ và Live đang bật → `start` lại với hồ sơ đó + gửi job `set_game` cho worker (thuật ngữ + overrides của game).
- Vùng ngoài màn hình (4a M3): kiểm tra pixel vùng nằm trong `QGuiApplication.screens()` → không thì báo 1 lần, không OCR.
- [ ] **Step 1:** Test (`foreground` tách phần Win32 sau một hàm giả được): cửa sổ dời `(100,50)→(400,300)` → ảnh chụp đúng vị trí mới; thu nhỏ → 0 job, `notify` 1 lần; `ignore` phủ toàn vùng → 0 job trong 3 s khi ảnh nhấp nháy; một vùng `name` chụp lỗi → chỉ số vùng `dialogue` không lệch; chuyển foreground sang game B có hồ sơ → `set_game` gửi đi, overlay game A đóng; migrate 4a giữ vùng cũ; chọn vùng ba bước lưu đủ `dialogue`/`name`/`choices`. FAIL → implement → PASS.
- [ ] **Step 2:** Commit `feat(windows): per-game live profiles`.

### Task 4: Windows — sửa bản dịch

**Files:** Create `windows/app/gui/correct_dialog.py`; Modify `windows/app/gui/overlay.py` (nút "Sửa"), `windows/app/main.py` (phím `edit_last` mặc định `ctrl+alt+e`, tray "Sửa bản dịch gần nhất"), `windows/app/config.py` (`hotkeys.edit_last`), `windows/app/gui/worker.py` (job `correct`); Test `windows/tests/test_correct_dialog.py`, `windows/tests/test_app.py`

**Interfaces:**
- `CorrectDialog(segments: list[Segment])` — mỗi câu: bản gốc (chỉ đọc) + ô sửa bản dịch; ô "Thuật ngữ" dạng `nguồn = đích` (đích trống → `keep`); `accepted -> list[Correction]`, `Correction(source, machine, corrected)` chỉ gồm câu đã đổi, `terms: list[tuple[str, str | None]]`.
- Job `correct` (worker thread): `pipeline.correct(...)` từng câu, `glossary.add_entry(...)`, ghi hồ sơ (`overrides`) và file thuật ngữ game (`data_dir/glossary/games/<id>.json`, tạo nếu chưa có — không ghi vào thư mục cài đặt).
- Sửa xong: overlay đang hiện cập nhật ngay; Live dùng bản sửa ở lần dịch sau.
- [ ] **Step 1:** Test: dialog chỉ trả câu đã đổi; thuật ngữ `Arcanist =` → `keep`; `Ctrl+Alt+E` khi chưa có kết quả → báo "Chưa có bản dịch nào để sửa"; sửa → hồ sơ có override, `corrections.jsonl` có dòng, overlay hiện bản sửa. FAIL → implement → PASS.
- [ ] **Step 2:** Commit `feat(windows): correct translations from the overlay`.

### Task 5: Android — nhận game, hồ sơ, sửa bản dịch

**Files:** Create `android/app/src/main/kotlin/dev/screentrans/profile/{GameDetector.kt, ProfileRepo.kt}`, `android/app/src/main/kotlin/dev/screentrans/ui/CorrectView.kt`; Modify `Controller.kt`, `live/LiveController.kt`, `ui/RegionEditView.kt` (chọn loại vùng), `ui/Results.kt` (nút "Sửa"), `MainActivity.kt` (nút cấp quyền Usage Access), `AndroidManifest.xml` (`PACKAGE_USAGE_STATS`), `engine/AppEngine.kt` (thuật ngữ + overrides theo game); app-core `ProfileLogic.kt`; Test `android/app-core/src/test/.../profile/ProfileLogicTest.kt`

**Interfaces:**
- app-core `ProfileLogic`: `pickGame(foreground: String?, manual: String?, own: String) -> String` (thủ công > foreground; app của mình / null → `_default`); `migratePrefs(regions: List<RelRect>, liveMode: String): Profile`; `orderedRegions(profile, mode): List<Pair<String, RelRect>>` (thứ tự `dialogue, name, choices` hoặc `area`).
- `GameDetector.current(): String?` — `UsageStatsManager.queryEvents` 10 s gần nhất, sự kiện `ACTIVITY_RESUMED` cuối cùng; không có quyền → `null`.
- `ProfileRepo` (filesDir/profiles/<package>.json) dùng `Profile.parse/serialize`.
- Menu nút nổi: "Game: <tên> ▸" (chọn tay trong danh sách hồ sơ + "Tự nhận"), "Sửa bản dịch gần nhất"; `RegionEditView` có nút chọn loại vùng (Thoại / Tên / Lựa chọn / Bỏ qua).
- `CorrectView`: overlay **focusable** (bàn phím) với một ô sửa mỗi câu + ô thuật ngữ; lưu → `engine.submit` job sửa (cùng luồng engine) → hồ sơ + `corrections.jsonl` trong filesDir.
- Live FLAG_SECURE (4a M7): khung Live đen + OCR rỗng → báo một lần như chế độ một lần.
- [ ] **Step 1:** Test JVM `ProfileLogic` (chọn game, migrate, thứ tự vùng) + engine job sửa ghi override và dùng ngay ở job sau. FAIL → implement → PASS.
- [ ] **Step 2:** Implement glue; CI `build-android` xanh. Commit `feat(android): per-game profiles and corrections`.

### Task 6: Nghiệm thu, đo FPS, tài liệu, release v0.1.0

**Files:** Create `CHANGELOG.md`; Modify `AGENT.md` (tick Phase 4, số đo), `README.md`, `windows/app/__init__.py` (`__version__ = "0.1.0"`), `.github/workflows/release.yml` (ghi chú phát hành lấy từ `CHANGELOG.md`)

- [ ] **Step 1 — cùng người dùng** (Reverse: 1999 trên cả hai máy):
  - [ ] Hồ sơ tự tạo khi chọn vùng lần đầu; mở lại app → tự nhận game, Live dùng đúng vùng.
  - [ ] Dời / phóng to cửa sổ game (Windows) → Live vẫn đúng vùng.
  - [ ] Sửa một câu → lần sau hiện bản sửa; `corrections.jsonl` có dòng.
  - [ ] Thêm thuật ngữ `keep`/`map` → câu sau dùng đúng.
  - [ ] **FPS** game: tắt Live / bật Live đứng yên / bật Live khi thoại chạy (Windows: bộ đếm FPS của Xbox Game Bar; Android: tùy chọn nhà phát triển "Hiển thị tốc độ khung hình" hoặc bộ đếm của game). Mục tiêu: giảm ≤ 5%.
- [ ] **Step 2:** Ghi số đo vào AGENT.md, cập nhật README + CHANGELOG; chạy toàn bộ test; merge `phase-4b` vào `main`, push.
- [ ] **Step 3 — người dùng xác nhận trước:** `git tag v0.1.0 && git push origin v0.1.0` → workflow `release` xanh → release `v0.1.0` có `ScreenTrans-windows.zip` + `ScreenTrans-android.apk`.
