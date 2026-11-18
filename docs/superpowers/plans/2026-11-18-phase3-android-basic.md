# Phase 3 — App Android cơ bản (một lần + toàn màn hình) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App ScreenTrans trên Android (POCO X8 Pro): một **nút nổi** đè lên game, chạm mở menu **Dịch vùng / Toàn màn hình / Chọn vùng mới**; app chụp màn hình bằng MediaProjection, đọc chữ bằng ML Kit, dịch EN→VI ngay trên máy bằng opus-mt ONNX (`mt-core`), hiện bản dịch đè lên game; APK build trên CI.

**Architecture:** Hai module Kotlin JVM thuần, test được trên CI: `mt-core` (đã có: SentencePiece + giải mã ONNX) và **`text-core`** mới (hậu xử lý, thuật ngữ, cache, pipeline — bản port 1-1 của Python, pass **cùng fixtures** `shared/fixtures/postprocess`). Module `:app` là vỏ Android: `MainActivity` xin quyền → `CaptureService` (foreground, MediaProjection + VirtualDisplay + ImageReader) sở hữu nút nổi, overlay và một **`TranslationEngine` chạy trên đúng một luồng nền** (một `Pipeline` duy nhất, như Windows). Overlay được **ẩn trong lúc chụp** (Android không loại overlay khỏi ảnh chụp được).

**Tech Stack:** Kotlin 2.2.20, AGP 8.13.0, Gradle 8.14.3, JDK 17, ONNX Runtime 1.32.0 (Android/desktop), ML Kit Text Recognition (Latin, bundled), kotlinx-coroutines, Gson, JUnit 5.

**Spec:** [docs/superpowers/specs/2026-11-16-screentrans-design.md](../specs/2026-11-16-screentrans-design.md) (§5.1–5.4, §5.7–5.7b, §7), [AGENT.md](../../../AGENT.md) (§8–9, §11–13, Phase 3), kết quả Phase 0: [reports/2026-11-17-phase0-results.md](../reports/2026-11-17-phase0-results.md).

## Global Constraints

- minSdk **29**, targetSdk **36**; package/applicationId **`dev.screentrans`** (thay app spike `dev.screentrans.spike`).
- Dịch: **opus-mt-en-vi ONNX**, CPU **2 luồng**, greedy, không GPU/NNAPI/XNNPACK (Phase 0: 53 ms/câu, XNNPACK không lợi). `ortVersion` = `onnxruntime` Python = **1.32.0**.
- Nguồn tối đa **512** token (`MarianVocab.MAX_SRC`), đầu ra **256**; câu > **150** token tách tại `, ; :` rồi theo cụm từ (giống `split_long` Python).
- **Một `Pipeline` chỉ dùng trên một luồng** (`TranslationEngine`): UI không gọi pipeline trực tiếp; job mới thay job đang chờ.
- Thuật ngữ: placeholder **`[i]`**, ưu tiên game > tự động > chung giống Python; bảng lấy từ `shared/glossary/` (đóng vào assets).
- OCR: **ML Kit Text Recognition Latin bundled** (không cần Play Services tải model).
- Model **đóng trong APK** (assets, ~131 MB) và copy sang `filesDir` khi **phiên bản model khác** (không chỉ "file đã tồn tại" — lỗi nhỏ Phase 0).
- Overlay `TYPE_APPLICATION_OVERLAY`; overlay kết quả **ẩn khi chụp**, hiện lại sau. Nút nổi kéo được, nhớ vị trí.
- Ngân sách (AGENT.md §13, Android): dịch vùng ~50 từ **< 800 ms**; toàn màn hình: khối đầu **< 1 s**, tất cả ~20 khối **< 3 s**; RAM thêm **< 600 MB**.
- Không gửi chữ ra ngoài (không mạng trong Phase 3).
- Nhánh `phase-3`; xong thì merge vào `main` và push (không PR). Commit kết thúc `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Game chặn chụp màn hình (FLAG_SECURE) → ảnh đen** → báo "Game này chặn chụp màn hình", không dịch ảnh đen. Test thuần ở Task 5 (`isMostlyBlack`).
2. **Xoay màn hình / đổi độ phân giải khi đang chạy** → vùng chọn lưu theo **tỉ lệ 0–1** và ảnh chụp đúng kích thước mới. Test thuần ở Task 7 (`RelRect`), thử thật ở Task 10.
3. **Người dùng từ chối quyền overlay / chụp màn hình, hoặc Android 14+ dừng MediaProjection** (thu hồi từ thanh thông báo) → service dừng sạch, nút nổi biến mất, mở app báo cần cấp lại quyền; không crash. Test ở Task 4 (state machine `PermissionState`), thử thật ở Task 10.
4. **Bấm liên tục khi đang dịch** → không treo, chỉ job mới nhất chạy. Test ở Task 6.
5. **Chữ tiếng Việt hiển thị đúng dấu, ô dịch không tràn khỏi màn hình** → test thuần `placeOverlay`/`fitBlock` ở Task 8.

---

### Task 1: Chốt các chi tiết hậu xử lý còn mơ hồ (Python là chuẩn)

**Files:** Modify `shared/fixtures/postprocess/README.md`; Create fixtures mới trong `shared/fixtures/postprocess/`; Modify `windows/app/text/postprocess.py` nếu cần cho khớp README; Test `windows/tests/test_postprocess.py` (đã tham số hóa theo fixtures)

**Interfaces:**
- Produces: README ghi rõ (lỗi nhỏ từ review Phase 1): (a) thứ tự duyệt dòng `(top, left)`, hòa `bottom` khi chọn đoạn → **đoạn tạo trước**; (b) "chữ hoa" ở quy tắc 4/6 là **ASCII `A–Z`**; (c) "chữ cái/chữ số" ở quy tắc 1 = Unicode letter/digit theo Python `str.isalpha/isalnum` (Kotlin: `Char.isLetter/isLetterOrDigit` + ghi chú các khác biệt đã biết), tách token theo **khoảng trắng Unicode**; (d) quy tắc 6 kiểm tra viết tắt **sau khi bỏ dấu nháy mở** ở đầu token (`"Mr.` không tách); (e) quy tắc 4 đếm token **sau khi bỏ `:` cuối**.
- [ ] **Step 1:** Thêm fixtures: `quote_prefixed_abbrev` (`"Mr. Smith came." He left.` → 2 câu, không tách sau `"Mr.`), `name_with_colon_three_tokens` (`Old Man Tom:` → name), `tie_break_two_groups` (dòng nối được vào hai đoạn cùng `bottom` → vào đoạn tạo trước), `accented_name` (`Élise` 1 dòng trên thoại → **không** phải name vì không phải ASCII hoa — chốt hành vi hiện tại).
- [ ] **Step 2:** Chạy `pytest windows/tests/test_postprocess.py -q` → fixture nào FAIL thì sửa Python cho khớp README (Python vẫn là chuẩn). Expected cuối: PASS.
- [ ] **Step 3:** Commit `docs(shared): pin postprocess edge cases for the Kotlin port`.

### Task 2: `text-core` — hậu xử lý Kotlin

**Files:** Create `android/text-core/build.gradle.kts` (Kotlin JVM, toolchain 17, Gson, JUnit 5), `android/text-core/src/main/kotlin/screentrans/text/Line.kt`, `.../Postprocess.kt`; Test `android/text-core/src/test/kotlin/screentrans/text/PostprocessFixturesTest.kt`; Modify `android/settings.gradle.kts` (`include(":text-core")`)

**Interfaces:**
- Produces: `data class Line(val text: String, val left: Float, val top: Float, val width: Float, val height: Float)` (+ `right`, `bottom`); `enum class Kind { NAME, TEXT }`; `data class Paragraph(val kind: Kind, val text: String, val sentences: List<String>, val left: Float, val top: Float, val right: Float, val bottom: Float)`; `object Postprocess { fun run(lines: List<Line>): List<Paragraph>; fun splitSentences(text: String): List<String> }` — hằng số `JOIN_GAP=0.8, OVERLAP=0.5, NAME_GAP=2.0, SAME_ROW=0.5`.
- Test đọc thư mục fixtures qua system property `fixtures.dir` (Gradle đặt mặc định `<repo>/shared/fixtures/postprocess`), **mỗi file một test động** (`@TestFactory`), so `kind/text/sentences`.
- [ ] **Step 1:** Viết test (fixtures + `splitSentences` cùng bảng ví dụ như `windows/tests/test_postprocess.py::test_split_sentences`). `./gradlew :text-core:test` → FAIL.
- [ ] **Step 2:** Port `windows/app/text/postprocess.py` theo README. **Step 3:** PASS toàn bộ fixtures. **Step 4:** Commit `feat(android): kotlin postprocess passing shared fixtures`.

### Task 3: `text-core` — thuật ngữ, cache, pipeline

**Files:** Create `android/text-core/src/main/kotlin/screentrans/text/{Glossary.kt, ProperNounTracker.kt, TranslationCache.kt, Pipeline.kt, SplitLong.kt}`; Test tương ứng `GlossaryTest.kt`, `PipelineTest.kt`

**Interfaces:**
- Consumes: `Paragraph`, `Postprocess`.
- Produces:
  - `class Glossary(entries: List<Entry>)` + `companion fun load(vararg json: String): Glossary` (thứ tự = ưu tiên); `fun protect(text: String): Pair<String, List<String>>`; `fun restore(text: String, values: List<String>): String?`; `fun addKeep(term: String)`; `const val PLACEHOLDER = "[%d]"` — **cùng hành vi** `windows/app/glossary.py` (dài nhất trước, ranh giới từ, case_sensitive, ưu tiên theo thứ tự nạp, tracker thấp nhất).
  - `class ProperNounTracker(commonWords: Set<String>, minCount: Int = 3) { fun observe(sentence: String): List<String> }` (đếm **câu khác nhau**).
  - `class TranslationCache(maxItems: Int)` (LRU trong bộ nhớ; key = model id + câu chuẩn hóa).
  - `fun interface SentenceTranslator { fun translate(texts: List<String>): List<String> }`.
  - `fun splitLong(text: String, countTokens: (String) -> Int, limit: Int = 150): List<String>`.
  - `data class Segment(val kind: Kind, val source: String, val translation: String?, val left: Float, val top: Float, val right: Float, val bottom: Float)`.
  - `class Pipeline(translator: SentenceTranslator, modelId: String, glossary: Glossary, cache: TranslationCache, tracker: ProperNounTracker?)`: `fun translateParagraphs(ps: List<Paragraph>): List<Segment>` (1 batch); `fun iterSegments(ps: List<Paragraph>): Sequence<Segment>` (từng đoạn) — retry không placeholder khi `restore` trả `null`, **không cache** kết quả retry.
- [ ] **Step 1:** Test port trực tiếp các test Python tương ứng (`test_glossary.py`, `test_pipeline.py`, `test_split_long_*`) dùng chung `shared/glossary/*.json`. FAIL → **Step 2:** implement → **Step 3:** PASS. **Step 4:** Commit `feat(android): glossary, cache and pipeline in text-core`.

### Task 4: Vỏ app: quyền, service, thông báo

**Files:** Delete `android/app/src/main/kotlin/dev/screentrans/spike/BenchActivity.kt`; Modify `android/app/build.gradle.kts` (namespace/applicationId `dev.screentrans`, `versionName "0.1.0"`, deps `:text-core`, coroutines, ML Kit `com.google.mlkit:text-recognition:16.0.1`), `AndroidManifest.xml` (`FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PROJECTION`, `SYSTEM_ALERT_WINDOW`, `POST_NOTIFICATIONS`; `<service android:foregroundServiceType="mediaProjection">`); Create `android/app/src/main/kotlin/dev/screentrans/{MainActivity.kt, CaptureService.kt, PermissionState.kt}`; Test `android/app/src/test/kotlin/dev/screentrans/PermissionStateTest.kt` (JVM unit test)

**Interfaces:**
- Produces: `enum class Step { OVERLAY, NOTIFICATIONS, CAPTURE, RUNNING }`; `fun nextStep(canDrawOverlays: Boolean, notificationsOk: Boolean, serviceRunning: Boolean): Step` (thứ tự: overlay → thông báo (API 33+, bỏ qua nếu < 33 → truyền `true`) → xin MediaProjection → chạy). `MainActivity`: một màn hình, nút theo `nextStep` ("Cho phép hiện trên ứng dụng khác" → `Settings.ACTION_MANAGE_OVERLAY_PERMISSION`; "Cho phép thông báo"; "Bắt đầu" → `MediaProjectionManager.createScreenCaptureIntent()` → `CaptureService.start(context, resultCode, data)`; "Dừng"). `CaptureService`: `startForeground` với thông báo "ScreenTrans đang chạy" + action **Dừng**; `MediaProjection.Callback.onStop` → `stopSelf()`; companion `isRunning: StateFlow<Boolean>`.
- [ ] **Step 1:** Test `nextStep` cho mọi tổ hợp (vd `(false, *, *) → OVERLAY`, `(true, false, false) → NOTIFICATIONS`, `(true, true, false) → CAPTURE`, `(true, true, true) → RUNNING`). FAIL → implement `PermissionState.kt` → PASS.
- [ ] **Step 2:** Viết `MainActivity`, `CaptureService` (chưa chụp), manifest. `./gradlew :app:assembleDebug` trên CI (máy dev không có SDK — đẩy nhánh, chạy workflow ở Task 9 hoặc tạm dùng `android-spike.yml` đổi tên). Expected: build xanh.
- [ ] **Step 3:** Commit `feat(android): app shell with permissions and foreground service`.

### Task 5: Chụp màn hình

**Files:** Create `android/app/src/main/kotlin/dev/screentrans/capture/{ScreenCapturer.kt, Frames.kt}`; Test `android/app/src/test/kotlin/dev/screentrans/capture/FramesTest.kt`

**Interfaces:**
- Produces: `class ScreenCapturer(projection: MediaProjection, context: Context)`: tạo `VirtualDisplay` + `ImageReader(RGBA_8888, maxImages=2)` theo kích thước **thật** của màn hình (`WindowManager.currentWindowMetrics.bounds`), giữ suốt phiên (Android 14+: một token một VirtualDisplay); `suspend fun capture(): Bitmap` (frame mới nhất, bỏ padding `rowStride`); `fun resize()` khi xoay (`onConfigurationChanged` của service gọi); `fun release()`.
  - `Frames.isMostlyBlack(pixels: IntArray, threshold: Float = 0.98f): Boolean` (≥ 98% điểm ảnh có độ sáng < 8 → coi như game chặn chụp).
  - `Frames.crop(width: Int, height: Int, rect: android.graphics.Rect)` → rect kẹp trong ảnh (thuần, test được bằng số nguyên: `fun clampRect(w, h, l, t, r, b): IntArray`).
- [ ] **Step 1:** Test `isMostlyBlack` (mảng toàn `0xFF000000` → true; 5% điểm trắng → false), `clampRect` (rect tràn phải/dưới bị kẹp; rect ngoài ảnh → rỗng). FAIL → implement → PASS.
- [ ] **Step 2:** Implement `ScreenCapturer` và nối vào `CaptureService.onStartCommand`. Commit `feat(android): media projection capture`.

### Task 6: OCR + dịch trên luồng nền

**Files:** Create `android/app/src/main/kotlin/dev/screentrans/engine/{MlKitOcr.kt, ModelInstaller.kt, TranslationEngine.kt}`; Test `android/app/src/test/kotlin/dev/screentrans/engine/{ModelInstallerTest.kt, TranslationEngineTest.kt}`; Modify `android/mt-core` (thêm `fun countTokens(text: String): Int` vào `Translator` và áp `splitLong` khi dịch)

**Interfaces:**
- Consumes: `Postprocess`, `Pipeline`, `Glossary`, `mt-core Translator`.
- Produces:
  - `MlKitOcr.recognize(bitmap: Bitmap): List<Line>` (mỗi `Text.Line` → `Line` theo `boundingBox`, pixel ảnh).
  - `object ModelInstaller { fun needsCopy(installedVersion: String?, bundledVersion: String): Boolean; fun install(context): File }` — đọc `assets/model/VERSION`, copy toàn bộ `assets/model/*` sang `filesDir/model/` (file tạm rồi đổi tên), ghi `filesDir/model/VERSION` **sau cùng**.
  - `sealed interface Job { val id: Int; data class Region(...bitmap, rect...); data class FullScreen(...bitmap...) }`.
  - `class TranslationEngine(factory: () -> PipelineBundle, dispatcher: CoroutineDispatcher = newSingleThreadContext("translate"))` với `PipelineBundle(ocr: (Bitmap) -> List<Line>, pipeline: Pipeline)`; `val state: StateFlow<EngineState>` (`Loading`, `Ready`, `Failed(msg)`); `fun submit(job: Job)` (giữ **job mới nhất**, job chờ cũ → `Superseded`); `val events: SharedFlow<EngineEvent>` (`Segment(jobId, seg)`, `Done(jobId, segs)`, `JobFailed(jobId, why)`); làm nóng bằng một câu sau khi nạp.
- [ ] **Step 1:** Test JVM (factory giả, OCR giả, translator giả có trễ, `StandardTestDispatcher`/runTest): `needsCopy(null,"1")==true`, `("1","1")==false`, `("1","2")==true`; engine: Ready sau factory; job Region → `Done`; FullScreen → các `Segment` rồi `Done`; 3 job khi bận → job giữa `Superseded`; factory ném lỗi → `Failed(msg)` và job sau đó `JobFailed`. FAIL → implement → PASS.
- [ ] **Step 2:** `MlKitOcr` (không unit test — chạy thật ở Task 10). Commit `feat(android): ocr and single-thread translation engine`.

### Task 7: Nút nổi, menu, chọn vùng

**Files:** Create `android/app/src/main/kotlin/dev/screentrans/ui/{Bubble.kt, RegionSelectView.kt, RelRect.kt, Prefs.kt}`; Test `android/app/src/test/kotlin/dev/screentrans/ui/RelRectTest.kt`

**Interfaces:**
- Produces:
  - `data class RelRect(val l: Float, val t: Float, val r: Float, val b: Float)` (0–1 theo màn hình): `fun toPx(w: Int, h: Int): IntArray`; `companion fun fromPx(l, t, r, b, w, h): RelRect`; `fun isUsable(w, h): Boolean` (≥ 8 px mỗi chiều).
  - `Prefs`: lưu/đọc `RelRect` vùng dịch và vị trí nút nổi (SharedPreferences).
  - `Bubble`: view tròn 48 dp, kéo được (dính mép gần nhất khi thả), chạm → `PopupMenu` 3 mục **Dịch vùng** / **Toàn màn hình** / **Chọn vùng mới**; khi chưa có vùng, "Dịch vùng" mở chọn vùng.
  - `RegionSelectView`: overlay toàn màn hình nền tối 30%, kéo hình chữ nhật, nút **Xong**/**Huỷ**; trả `RelRect` qua callback.
- [ ] **Step 1:** Test `RelRect`: `fromPx(100,200,500,400,1000,2000) == RelRect(0.1,0.1,0.5,0.2)`; `toPx` trên màn hình xoay (2000×1000) cho rect đúng tỉ lệ; `isUsable` false khi 5 px. FAIL → implement → PASS.
- [ ] **Step 2:** Implement `Bubble`, `RegionSelectView`, `Prefs`, nối vào service. Commit `feat(android): floating bubble, menu and region selection`.

### Task 8: Hiện bản dịch

**Files:** Create `android/app/src/main/kotlin/dev/screentrans/ui/{ResultCard.kt, FullScreenLayer.kt, Layout.kt}`; Test `android/app/src/test/kotlin/dev/screentrans/ui/LayoutTest.kt`; Modify `CaptureService.kt` (luồng: ẩn overlay → đợi 1 frame (~50 ms) → chụp → hiện "Đang dịch…" → kết quả)

**Interfaces:**
- Produces:
  - `Layout.placeOverlay(region: IntArray /*l,t,r,b*/, w: Int, h: Int, screenW: Int, screenH: Int, gap: Int = 12): IntArray /*x,y*/` — **cùng quy tắc** `windows/app/gui/overlay.py::place_overlay` (dưới vùng, tràn thì trên, kẹp màn hình).
  - `Layout.fitBlock(textLen: Int, blockW: Int, blockH: Int, baseSp: Float, minSp: Float = 9f): Float` — ước lượng cỡ chữ (dùng `StaticLayout` ở UI; hàm thuần chỉ chọn trong [min, base] theo diện tích, có test).
  - `ResultCard`: thẻ nền tối 85%, chữ trắng, tên in đậm `[Tên]`, nút **Copy**; chạm ngoài → đóng.
  - `FullScreenLayer`: overlay phủ màn hình, mỗi `Segment` một ô đè đúng `left/top/right/bottom`, hiện dần; chip "Đang dịch…"; chạm ô → thẻ có câu gốc + Copy; chạm chỗ trống → đóng.
  - Ảnh đen (`isMostlyBlack`) → thẻ báo "Game này chặn chụp màn hình (FLAG_SECURE), không dịch được".
- [ ] **Step 1:** Test `placeOverlay` (cùng 4 ca như test Python `test_overlay.py`, đổi gap=12) và `fitBlock` (chữ ngắn → base; rất dài → min). FAIL → implement → PASS.
- [ ] **Step 2:** Implement UI + nối luồng trong service. Commit `feat(android): result card and full-screen layer`.

### Task 9: CI build APK

**Files:** Create `.github/workflows/build-android.yml`; Delete `.github/workflows/android-spike.yml`; Modify `.github/workflows/ci.yml` (job `android-unit`: `./gradlew :mt-core:test :text-core:test :app:testDebugUnitTest`), `.github/workflows/release.yml` (thêm job build Android, đính `.apk`), `android/app/build.gradle.kts` (assets: `shared/glossary` → `assets/glossary`; `signingConfigs.release` đọc env `ANDROID_KEYSTORE_PATH/ANDROID_KEYSTORE_PASSWORD/ANDROID_KEY_ALIAS/ANDROID_KEY_PASSWORD`, thiếu thì dùng debug)

**Interfaces:**
- `build-android.yml` (push `main` khi đổi `android/**`, `shared/**`, `models/**` + `workflow_dispatch` + `workflow_call`): Python 3.11 → `models.export onnx opus-mt-en-vi` + `models.onnx_ref golden` → copy ONNX + `vocab.json` + `sp_source.json` + `config.json` vào `android/app/src/main/assets/model/` và ghi `VERSION` = `opus-mt-en-vi-onnx-<sha ngắn của commit models/>`; JDK 17; `./gradlew :mt-core:test :text-core:test :app:testDebugUnitTest` (golden thật); giải mã secret `ANDROID_KEYSTORE_BASE64` (nếu có) → `assembleRelease`; upload artifact `ScreenTrans-android.apk`.
- [ ] **Step 1:** Viết workflow; push nhánh; chạy `workflow_dispatch` trên nhánh (hoặc trigger push) → Expected: job xanh, artifact APK ~150–180 MB.
- [ ] **Step 2 — nhờ người dùng (để cập nhật APK không phải gỡ app cũ):** tạo keystore riêng (mình đưa lệnh `keytool`), thêm 4 secret vào GitHub. Không có secret → APK ký debug (mỗi lần cài bản mới phải gỡ bản cũ).
- [ ] **Step 3:** Commit `ci: build signed android apk`.

### Task 10: Nghiệm thu trên POCO X8 Pro + tài liệu

**Files:** Modify `AGENT.md` (tick Phase 3, số đo), `README.md` (cài APK, cấp quyền, dùng nút nổi)

- [ ] **Step 1 — cùng người dùng, Reverse: 1999 trên điện thoại:**
  - [ ] Cài APK, cấp quyền overlay + thông báo + chụp màn hình; nút nổi hiện, kéo được, nhớ vị trí.
  - [ ] **Chọn vùng mới** trên khung thoại → **Dịch vùng**: bản dịch đúng, đo thời gian (mục tiêu < 800 ms).
  - [ ] **Toàn màn hình** trên màn hình Log: khối đầu < 1 s, tất cả < 3 s, ô đè đúng chỗ, chạm ô xem câu gốc.
  - [ ] Xoay màn hình / đổi game → vùng vẫn đúng tỉ lệ.
  - [ ] Thu hồi chụp màn hình từ thanh thông báo → service dừng, nút nổi biến mất, không crash.
  - [ ] Dùng 15 phút: máy có nóng/hao pin bất thường không; game có giật không.
- [ ] **Step 2:** Ghi số đo vào AGENT.md, cập nhật README; chạy toàn bộ test; commit `docs: phase 3 usage and acceptance`; merge `phase-3` vào `main`, push.
