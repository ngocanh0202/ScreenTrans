# Phase 2 — App Windows có giao diện (một lần + toàn màn hình) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một app chạy nền trên khay hệ thống: `Ctrl+Alt+T` kéo chọn vùng → khung dịch nổi cạnh vùng; `Ctrl+Alt+F` → dịch toàn màn hình, bản dịch đè đúng chỗ từng khối chữ; model tải/chạy ở luồng riêng; có bản `.exe` build trên CI và model tải từ GitHub Releases.

**Architecture:** PySide6 trên luồng UI; một `TranslationWorker` (QObject trong QThread riêng) **sở hữu duy nhất một `Pipeline`** (quy ước Phase 1) — nạp model, làm nóng, nhận job, phát tín hiệu theo từng đoạn dịch xong. Phím tắt toàn cục qua Win32 `RegisterHotKey` + `QAbstractNativeEventFilter`. Toạ độ vùng chọn lấy bằng `GetCursorPos` (pixel vật lý, tiến trình per-monitor DPI aware v2) để khớp ảnh `mss`; vẽ overlay đổi pixel vật lý → toạ độ logic Qt theo `devicePixelRatio` của màn hình đó.

**Tech Stack:** Python 3.11, PySide6, pytest-qt, ctypes (Win32), mss, PyInstaller, GitHub Actions + `gh` CLI (Releases).

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md) (§5.6–5.7b, §6, §7), [AGENT.md](../../../AGENT.md) (§7, §11–13, Phase 2).

## Global Constraints

- Python 3.11, `.venv` ở gốc repo; test `.venv\Scripts\python -m pytest -q`; CI `-m "not local"` với `QT_QPA_PLATFORM=offscreen`.
- **Một `Pipeline` chỉ dùng trong một luồng** (luồng worker) — UI không bao giờ gọi pipeline trực tiếp.
- Phím tắt mặc định: `ctrl+alt+t` (dịch vùng), `ctrl+alt+f` (toàn màn hình); `ctrl+alt+l` (Live) **chỉ đăng ký ở Phase 4**.
- Overlay: nền tối bán trong suốt (`overlay.opacity` mặc định 0.85), chữ trắng, **Segoe UI**, cỡ `overlay.font_size` (14), `overlay.show_source`; không bao giờ lọt vào ảnh chụp (`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE=0x11)`).
- Khung dịch một lần: **ngay dưới vùng chọn, tràn màn hình thì đặt phía trên**; đóng bằng **Esc** hoặc **click ra ngoài**; có nút **Copy**.
- Hiện **"Đang tải model…"** khi model chưa sẵn sàng, **"Đang dịch…"** khi job chạy quá **300 ms**.
- Toàn màn hình: chụp **màn hình đang chứa con trỏ**; khối dịch xong **hiện dần** (trên → dưới); mục tiêu khối đầu < 1 s, tất cả ~20 khối < 5 s (vinai).
- Game phải chạy cửa sổ/borderless (spec §3); không hook DirectX.
- Model mặc định `vinai-en2vi`; model tải theo manifest trên **GitHub Releases** (repo đã public) — không cần Hugging Face.
- **Dời sang Phase 4** (cần hồ sơ game): nút "Dùng khối này làm vùng Live" và nút **Sửa** bản dịch (`overrides`/`corrections.jsonl`). Phase 2 chỉ có Copy.
- Đẩy thẳng lên `main` khi xong phase (không PR). Commit kết thúc `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Bấm phím tắt khi model đang tải / đang dịch job trước** → không treo, không mất phím; job mới thay job đang chờ (chỉ giữ job mới nhất), khung hiện "Đang tải model…". Test ở Task 4.
2. **Màn hình 125%/150% và nhiều màn hình** → vùng chụp khớp đúng chỗ đã kéo. Test thuần đổi toạ độ ở Task 5/7 + checklist thủ công Task 11.
3. **Phím tắt đã bị app khác chiếm** → app vẫn chạy, báo trên tray "Không đăng ký được Ctrl+Alt+T", không crash. Test ở Task 3.
4. **Vùng chọn quá nhỏ (< 8 px) hoặc bấm Esc khi đang chọn** → huỷ, không chạy OCR. Test ở Task 5.
5. **Thiếu model khi chạy bản `.exe` lần đầu / mất mạng** → khung báo lỗi rõ (thông điệp `ModelNotFound`/`ModelDownloadError`), app vẫn sống, tray cho "Thử lại". Test ở Task 4/8.

---

### Task 1: Đường dẫn tài nguyên + phụ thuộc GUI

**Files:**
- Create: `windows/app/paths.py`; Test: `windows/tests/test_paths.py`
- Modify: `windows/app/glossary.py` (dùng `paths`), `windows/app/cli.py` (`DEFAULT_CONFIG` qua `paths`), `windows/requirements.txt` (+`PySide6`), `windows/requirements-dev.txt` (+`pytest-qt`, `pyinstaller`), `pytest.ini` (`qt_api = pyside6`), `.github/workflows/ci.yml` (env `QT_QPA_PLATFORM: offscreen`)

**Interfaces:**
- Produces: `resource_root() -> Path` — `Path(sys._MEIPASS)` khi chạy bản đóng gói (`getattr(sys, "frozen", False)`), ngược lại gốc repo; `shared_dir() -> Path` = `resource_root() / "shared"`; `default_config_path() -> Path` = `resource_root() / "windows" / "config.yaml"`.
- `glossary.COMMON_GLOSSARY`, `COMMON_WORDS`, `games_dir()` đều tính từ `shared_dir()`.

- [ ] **Step 1:** Test: không frozen → `shared_dir() / "glossary" / "common.json"` tồn tại; monkeypatch `sys.frozen=True`, `sys._MEIPASS=tmp_path` → `resource_root() == tmp_path`, `default_config_path() == tmp_path/"windows"/"config.yaml"`.
- [ ] **Step 2–4:** FAIL → implement + sửa glossary/cli dùng `paths` → PASS; toàn bộ suite xanh.
- [ ] **Step 5:** Commit `feat(windows): resource paths for packaged app; gui deps`.

### Task 2: Dịch dần từng đoạn (progressive)

**Files:** Modify `windows/app/pipeline.py`; Test `windows/tests/test_pipeline.py`

**Interfaces:**
- Produces: `Pipeline.iter_segments(paragraphs: list[Paragraph]) -> Iterator[Segment]` — trả **theo thứ tự đoạn**; đoạn `name` trả ngay; mỗi đoạn `text` dịch bằng **một** lời gọi translator cho các câu của nó (cùng cache/thuật ngữ/retry/tracker như `translate_paragraphs`). `translate_paragraphs` giữ nguyên hành vi (1 batch cho mọi câu) — dùng cho chế độ một lần.
- [ ] **Step 1:** Test: 3 đoạn (name, text 2 câu, text 1 câu) → `iter_segments` yield 3 segment theo thứ tự; translator nhận 2 lời gọi `[2 câu]`, `[1 câu]`; segment 1 yield **trước** khi lời gọi thứ hai diễn ra (translator giả ghi thời điểm gọi, generator lấy từng phần tử); câu đã có cache không gọi translator.
- [ ] **Step 2–4:** FAIL → implement (tách phần dịch 1 nhóm câu thành helper dùng chung) → PASS. **Step 5:** Commit `feat(windows): progressive per-paragraph translation`.

### Task 3: Phím tắt toàn cục

**Files:** Create `windows/app/gui/__init__.py`, `windows/app/gui/hotkeys.py`; Test `windows/tests/test_hotkeys.py`

**Interfaces:**
- Produces:
  - `parse_hotkey(s: str) -> tuple[int, int]` → `(modifiers, vk)`; modifiers Win32 `MOD_ALT=1, MOD_CONTROL=2, MOD_SHIFT=4, MOD_WIN=8` cộng `MOD_NOREPEAT=0x4000`; phím: `a`–`z`, `0`–`9`, `f1`–`f12`; sai → `ValueError`.
  - `class HotkeyManager(QObject)`: `register(name: str, combo: str) -> bool` (False nếu `RegisterHotKey` thất bại); signal `triggered(str)` (tên); `unregister_all()`; lắp `QAbstractNativeEventFilter` bắt `WM_HOTKEY=0x0312` (msg `wParam` = id).
- [ ] **Step 1:** Test: `parse_hotkey("ctrl+alt+t") == (0x4000|2|1, 0x54)`; `"Ctrl + Shift + F5"` → `(0x4000|2|4, 0x74)`; `"alt"`, `"ctrl+alt+ü"`, `""` → `ValueError`; `@local`: đăng ký cùng combo hai lần trên hai manager → lần hai trả `False`; mô phỏng `nativeEventFilter` với msg WM_HOTKEY id đúng → `triggered` phát tên (qtbot.waitSignal).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): global hotkeys`.

### Task 4: Worker dịch nền

**Files:** Create `windows/app/gui/worker.py`; Test `windows/tests/test_worker.py`

**Interfaces:**
- Consumes: `Pipeline`, `Segment`, `postprocess`, `build_pipeline`-tương đương (factory).
- Produces:
  - `@dataclass Job(id: int, mode: Literal["region","fullscreen"], image: PIL.Image.Image, origin: tuple[int,int])` (`origin` = toạ độ vật lý góc trên-trái của ảnh trên màn hình ảo).
  - `class TranslationWorker(QObject)`: `__init__(factory: Callable[[], Pipeline])`; slot `start()` (chạy trong thread: gọi factory → nạp model → `warm_up` nếu có → phát `ready()`; lỗi `ModelNotFound`/`ModelDownloadError`/`OcrUnavailable`/khác → `failed(str)`); slot `submit(job: Job)`; signals `ready()`, `failed(str)`, `progress(int, int)` (byte tải model), `job_started(int)`, `segment(int, object)` (job id, Segment — chỉ fullscreen), `job_done(int, object)` (job id, `list[Segment]`), `job_failed(int, str)`.
  - Hàng đợi **chỉ giữ job mới nhất**: job đến khi đang bận thay job chờ cũ (job cũ nhận `job_failed(id, "superseded")`); job đến trước `ready` được giữ và chạy ngay khi sẵn sàng.
  - `def start_worker(factory) -> tuple[QThread, TranslationWorker]` (moveToThread, nối `started→start`).
- [ ] **Step 1:** Test (pytest-qt, factory trả `Pipeline` với `FakeOcr`+`FakeTranslator` có `time.sleep` nhỏ): `ready` phát; job region → `job_done` có segments; job fullscreen → `segment` phát lần lượt rồi `job_done`; gửi 3 job khi bận → job giữa nhận `superseded`, job cuối chạy; factory ném `ModelNotFound("x")` → `failed` chứa `"x"`, job gửi sau đó nhận `job_failed`; job gửi **trước** `ready` vẫn chạy sau khi ready.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): background translation worker`.

### Task 5: Chọn vùng (selector)

**Files:** Create `windows/app/gui/selector.py`, `windows/app/gui/win32.py`; Test `windows/tests/test_selector.py`

**Interfaces:**
- Produces:
  - `win32.cursor_pos_physical() -> tuple[int, int]` (`GetCursorPos`, tiến trình DPI aware v2 → pixel vật lý); `win32.exclude_from_capture(hwnd: int) -> bool`; `win32.monitor_rect_at(x: int, y: int) -> tuple[int,int,int,int]` (`MonitorFromPoint` + `GetMonitorInfo`, vật lý).
  - `normalize_rect(x0, y0, x1, y1) -> tuple[int,int,int,int]` (left, top, width, height; kéo ngược chiều vẫn đúng).
  - `MIN_SIZE = 8`.
  - `class RegionSelector(QObject)`: `begin()` mở **một cửa sổ phủ mỗi `QScreen`** (frameless, on-top, nền tối 30%, con trỏ chữ thập), vẽ hình chữ nhật theo chuột (toạ độ logic để vẽ); **toạ độ trả về lấy từ `cursor_pos_physical()` lúc nhấn và lúc thả**; signal `selected(tuple)` (x, y, w, h vật lý) hoặc `cancelled()` khi Esc / chuột phải / vùng < `MIN_SIZE`.
- [ ] **Step 1:** Test: `normalize_rect(100,50,20,10) == (20,10,80,40)`; selector offscreen: mô phỏng press/release với `cursor_pos_physical` monkeypatch trả (10,10) rồi (210,110) → `selected((10,10,200,100))`; (10,10)→(14,12) → `cancelled`; Esc → `cancelled`; số cửa sổ mở = số `QGuiApplication.screens()`; sau khi kết thúc mọi cửa sổ đóng.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): region selector with physical coordinates`.

### Task 6: Khung dịch một lần

**Files:** Create `windows/app/gui/overlay.py`; Test `windows/tests/test_overlay.py`

**Interfaces:**
- Consumes: `Segment`, `Config.overlay`.
- Produces:
  - `place_overlay(region: QRect, size: QSize, screen: QRect, gap: int = 6) -> QPoint` — toạ độ logic: dưới vùng (`region.bottom()+gap`), căn trái theo vùng và kẹp trong `screen`; nếu đáy tràn `screen` → đặt trên (`region.top()-gap-size.height()`); nếu cả hai đều tràn → đè phía trong đáy màn hình.
  - `physical_to_logical(rect_phys: tuple, screen) -> QRect` dùng `screen.geometry()` + `devicePixelRatio()` (vùng trên màn hình chứa điểm giữa).
  - `class ResultOverlay(QWidget)`: `show_loading(text: str)`, `show_segments(segments: list[Segment], show_source: bool)`, `show_error(text: str)`; tên in đậm `[Tên]`, mỗi đoạn một khối; nút **Copy** (copy toàn bộ bản dịch, nối bằng `\n`); Esc / click ra ngoài (`focusOut` hoặc filter chuột toàn cục) → `close`; chiều rộng tối đa = max(vùng, 420 px) và ≤ 90% màn hình; gọi `exclude_from_capture` khi hiện.
- [ ] **Step 1:** Test: `place_overlay(QRect(100,100,400,80), QSize(400,120), QRect(0,0,1920,1080))` → `QPoint(100,186)`; vùng sát đáy (y=1000) → đặt trên `y = 1000-6-120`; vùng sát phải → x kẹp `1920-400`; `physical_to_logical((300,300,600,150), screen dpr 1.5 tại (0,0))` → `QRect(200,200,400,100)`; widget offscreen: `show_segments` với name+text → `text()` của label chứa `[Druvis III]` và bản dịch; Copy → clipboard = bản dịch; `show_source=True` có dòng tiếng Anh; Esc đóng.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): one-shot result overlay`.

### Task 7: Chế độ toàn màn hình

**Files:** Create `windows/app/gui/fullscreen.py`; Test `windows/tests/test_fullscreen.py`

**Interfaces:**
- Consumes: `physical_to_logical`, `exclude_from_capture`, `Segment` (box theo pixel ảnh), `Job.origin`.
- Produces:
  - `block_rect(segment_box: tuple[float,float,float,float], origin: tuple[int,int]) -> tuple[int,int,int,int]` — box ảnh + origin → rect vật lý (x, y, w, h).
  - `class FullscreenOverlay(QWidget)` phủ đúng màn hình được chụp: `add_segment(seg: Segment, origin)` vẽ một ô nền tối đè đúng vị trí khối (chữ co từ `font_size` xuống tối thiểu 9 cho vừa ô, cho phép cao hơn khối gốc 50% rồi cắt bằng "…"); khối `name` vẽ nhãn nhỏ không nền; chip "Đang dịch…" ở góc trên-phải tới khi `finish()`; click một ô → popup nhỏ có bản gốc + **Copy**; Esc / click vùng trống → đóng; `exclude_from_capture`.
- [ ] **Step 1:** Test: `block_rect((10,20,110,60),(1920,0)) == (1930,20,100,40)`; offscreen: 3 `add_segment` → 3 ô ở vị trí logic đúng (dpr 1.0 và 1.5); ô hiện ngay sau `add_segment` (không đợi `finish`); text dài → font ≥ 9 và có "…"; Esc đóng.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): full-screen translation overlay`.

### Task 8: App khay hệ thống (ghép nối)

**Files:** Create `windows/app/main.py`, `windows/app/__main__.py` (gọi `main`); Modify `windows/app/cli.py` (tách `build_pipeline` dùng chung → `windows/app/factory.py`); Test `windows/tests/test_app.py`

**Interfaces:**
- Consumes: mọi Task trên; `ensure_model(progress=...)`.
- Produces:
  - `factory.build_pipeline(config: Config, model_dir: Path | None, glossaries: list[Path], progress: Callable[[int,int],None] | None = None) -> Pipeline` (CLI và GUI dùng chung).
  - `class TrayApp(QObject)`: `__init__(config: Config, worker_factory=start_worker, hotkeys: HotkeyManager | None = None)`; tray menu: **Dịch vùng (Ctrl+Alt+T)**, **Toàn màn hình (Ctrl+Alt+F)**, dòng trạng thái model (Đang tải… x/y MB / Sẵn sàng: vinai-en2vi / Lỗi), **Thử lại** (khi lỗi), **Model ▸ vinai-en2vi / opus-mt-en-vi** (đổi → khởi động lại worker), **Mở thư mục dữ liệu**, **Thoát**. Icon vẽ bằng `QPainter` (chữ "T" trắng trên nền xanh), không cần file ảnh.
  - Luồng một lần: hotkey → `RegionSelector.begin()` → `selected` → `capture_region` → `Job("region")` → hiện `ResultOverlay` "Đang dịch…" sau 300 ms (hoặc "Đang tải model…" nếu chưa ready) → `job_done` → `show_segments`; `job_failed` (trừ `superseded`) → `show_error`.
  - Luồng toàn màn hình: hotkey → `monitor_rect_at(cursor)` → chụp → `FullscreenOverlay` → `segment` → `add_segment` → `job_done` → `finish()`.
  - `main(argv=None) -> int`: `QApplication` (quitOnLastWindowClosed=False), `--config`, `--self-test` (nạp config + glossary + tạo icon, in `OK`, thoát 0 — dùng cho CI kiểm bản `.exe`).
  - Phím tắt đăng ký thất bại → tray thông báo `Không đăng ký được <combo>` (balloon), app vẫn chạy.
- [ ] **Step 1:** Test offscreen với worker giả (đồng bộ) + `HotkeyManager` giả: phát `triggered("translate_region")` → selector giả trả vùng → overlay nhận segments; khi worker chưa ready → overlay "Đang tải model…" rồi tự cập nhật khi ready; worker `failed` → menu có "Thử lại", bấm → factory gọi lần 2; đổi model trong menu → factory gọi với model mới; hotkey đăng ký fail → thông báo chứa `Ctrl+Alt+T`; `main(["--self-test"]) == 0` in `OK`. CLI test cũ vẫn xanh sau khi tách `factory`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat(windows): tray app wiring`.

### Task 9: Model trên GitHub Releases

**Files:** Modify `.github/workflows/models.yml`, `models/manifest.py`, `models/tests/test_manifest.py`, `windows/config.yaml`, `windows/app/config.py` (mặc định `manifest_url`)

**Interfaces:**
- Produces: release tag `models-v<version>`; asset tên phẳng `"{id}__{format}__{path với / → __}"`; manifest `url` = `https://github.com/ngocanh0202/ScreenTrans/releases/download/models-v{version}/{asset}`; `manifest.json` là một asset của cùng release. `build_manifest(..., asset_url: Callable[[str,str,str,str], str] | None)` (mặc định cách cũ) và CLI `--github-release REPO` để dùng kiểu GitHub. `models.manifest_url` mặc định → `https://github.com/ngocanh0202/ScreenTrans/releases/download/models-v1/manifest.json`.
- `models.yml`: bỏ bước Hugging Face; `permissions: contents: write`; sau stage → `gh release create models-v${{inputs.version}} --title ... --notes ...` (nếu đã có thì `gh release upload --clobber`) với mọi file phẳng + `manifest.json`, `GH_TOKEN: ${{ github.token }}`.
- [ ] **Step 1:** Test `build_manifest` kiểu GitHub: url của `sub/vocab.json` của `vinai-en2vi` ct2 = `.../models-v3/vinai-en2vi__ct2__sub__vocab.json`; hai model trùng tên file không trùng asset.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat: publish models to GitHub Releases`.
- [ ] **Step 6 — nhờ người dùng:** Actions → **models** → Run workflow (version `1`). Expected: release `models-v1` có ~25 asset; mở `manifest_url` tải được JSON.

### Task 10: Đóng gói `.exe` + CI

**Files:** Create `windows/screentrans.spec`, `.github/workflows/build-windows.yml`, `.github/workflows/release.yml`

**Interfaces:**
- Produces: PyInstaller **onedir**, `--noconsole`, tên `ScreenTrans`, entry `windows/app/__main__.py`, kèm `shared/glossary/**`, `shared/fixtures` **không** kèm, `windows/config.yaml` → `windows/config.yaml` trong bundle (khớp `paths.default_config_path`). Artifact `ScreenTrans-windows.zip`.
- `build-windows.yml` (push `main` + `workflow_dispatch`, `windows-latest`): cài deps + pyinstaller → build → chạy `dist/ScreenTrans/ScreenTrans.exe --self-test` (Expected in `OK`, exit 0) → zip → upload artifact.
- `release.yml` (tag `v*`): gọi build như trên, `gh release create $TAG ScreenTrans-windows.zip`.
- [ ] **Step 1:** Build local: `.venv\Scripts\pyinstaller windows\screentrans.spec --noconfirm` → Expected: `dist\ScreenTrans\ScreenTrans.exe --self-test` in `OK`. Ghi dung lượng thư mục.
- [ ] **Step 2:** Viết 2 workflow; commit `ci: build windows exe and release on tag`; push `main` → nhờ người dùng xác nhận job xanh.

### Task 11: Nghiệm thu thủ công + tài liệu

**Files:** Modify `AGENT.md` (tick Phase 2, số đo), `README.md` (cách dùng app)

- [ ] **Step 1 — cùng người dùng, trên game thật (cửa sổ/borderless):** checklist, ghi kết quả vào AGENT.md:
  - [ ] `Ctrl+Alt+T` khi đang chơi: chọn khung thoại → khung dịch hiện dưới vùng, đúng chữ; Esc và click ngoài đều đóng; Copy dán ra đúng.
  - [ ] Windows scale **100% và 125%/150%** (Settings → Display): vùng dịch khớp chỗ đã kéo.
  - [ ] Nếu có 2 màn hình: chọn vùng ở màn hình phụ.
  - [ ] `Ctrl+Alt+F` trên màn hình Log: khối đầu < 1 s, tất cả < 5 s; ô dịch nằm đúng chỗ; click một ô xem bản gốc.
  - [ ] Đổi model sang opus trong tray → dịch nhanh hơn; đổi lại vinai.
  - [ ] FPS game trước/sau khi bật app (công cụ FPS của game hoặc Xbox Game Bar): không giảm rõ rệt khi app nhàn rỗi.
- [ ] **Step 2:** Cập nhật README (tải zip từ Actions/Release, chạy `ScreenTrans.exe`, lần đầu tự tải model ~440 MB, phím tắt) và AGENT.md; chạy toàn bộ test; commit `docs: phase 2 usage and acceptance`; push `main`.
