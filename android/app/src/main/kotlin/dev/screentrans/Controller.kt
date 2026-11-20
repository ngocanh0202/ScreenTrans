package dev.screentrans

import android.content.Context
import android.graphics.Bitmap
import android.content.ContentValues
import android.graphics.Color
import android.provider.MediaStore
import android.os.Build
import android.media.projection.MediaProjection
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowManager
import dev.screentrans.capture.ScreenCapturer
import android.content.Intent
import android.provider.Settings
import dev.screentrans.core.EngineControl
import dev.screentrans.core.EngineEvent
import dev.screentrans.core.EngineJob
import dev.screentrans.core.EngineState
import dev.screentrans.core.CaptureProbe
import dev.screentrans.core.Frames
import dev.screentrans.core.Layout
import dev.screentrans.core.RelRect
import dev.screentrans.core.SUPERSEDED
import dev.screentrans.core.TranslationEngine
import dev.screentrans.engine.AppEngine
import dev.screentrans.core.live.LiveParams
import dev.screentrans.core.profile.Profile
import dev.screentrans.core.profile.ProfileLogic
import dev.screentrans.live.LiveController
import dev.screentrans.profile.GameDetector
import dev.screentrans.profile.ProfileRepo
import dev.screentrans.core.ui.PanelAction
import dev.screentrans.core.ui.PanelEffect
import dev.screentrans.core.ui.PanelState
import dev.screentrans.core.ui.TranslateMode
import dev.screentrans.ui.ControlPanel
import dev.screentrans.ui.PanelTile
import dev.screentrans.ui.SettingsPanel
import dev.screentrans.ui.SettingsValues
import dev.screentrans.ui.CorrectView
import dev.screentrans.ui.Fix
import dev.screentrans.ui.LlmPanel
import dev.screentrans.ui.LlmValues
import dev.screentrans.ui.Bubble
import dev.screentrans.ui.FullScreenLayer
import dev.screentrans.ui.MenuPanel
import dev.screentrans.ui.Overlays
import dev.screentrans.ui.Prefs
import dev.screentrans.ui.RegionEditView
import dev.screentrans.ui.ResultCard
import dev.screentrans.ui.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import screentrans.text.Kind
import screentrans.text.Segment
import screentrans.text.normalizeText
import java.util.concurrent.Executors

/**
 * Everything the service shows: bubble -> menu -> capture (overlays hidden) -> engine -> results.
 * Lives on the main thread; OCR + translation run on the engine's single thread.
 */
private const val BLOCKED = "Game này chặn chụp màn hình (FLAG_SECURE), không dịch được."

class Controller(private val context: Context, projection: MediaProjection) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val engineThread = Executors.newSingleThreadExecutor { r -> Thread(r, "screentrans-engine") }
    private val capturer = ScreenCapturer(projection, context)
    private val overlays = Overlays(context)
    private val prefs = Prefs(context)
    // Live OCR on its own thread: a slow (remote) translation never stops Live from reading the screen
    private val ocrThread = Executors.newSingleThreadExecutor { r -> Thread(r, "screentrans-live-ocr") }
    private val engine = TranslationEngine({ AppEngine.bundle(context) }, scope, engineThread.asCoroutineDispatcher(),
        ocrDispatcher = ocrThread.asCoroutineDispatcher())

    private val bubble = Bubble(context, onTap = ::showMenu, onMoved = { x, y -> prefs.bubbleX = x; prefs.bubbleY = y })
    private var menu: View? = null
    private val cards = mutableListOf<ResultCard>()
    private var layer: FullScreenLayer? = null
    private var selector: View? = null
    private var nextId = 1
    private var regionJob = -1
    private var regionsPx: List<IntArray> = emptyList()
    private var fullJob = -1
    private val maybeBlocked = HashSet<Int>()  // jobs whose frame looked black (FLAG_SECURE?)
    private val repo = ProfileRepo(context)
    private val detector = GameDetector(context)
    private var engineGame: String? = null       // profile whose glossary / overrides the engine uses
    private var liveGame: String? = null
    private var lastSegments: List<Segment> = emptyList()  // last one-shot result, for "Sửa"
    private var correctView: View? = null
    // Live notices are toasts: a result card would pause Live until it is closed.
    private val live = LiveController(context, scope, capturer, engine, overlays, newId = { nextId++ },
        notify = { msg -> android.widget.Toast.makeText(context, msg, android.widget.Toast.LENGTH_LONG).show() },
        hideOthers = { hidden -> bubble.visibility = if (hidden) View.INVISIBLE else View.VISIBLE },
    )
    private var restartLiveOnClose = false  // settings changed while Live runs: redraw with them

    fun start() {
        repo.migrateOnce(prefs)
        scope.launch { engine.events.collect(::onEvent) }  // collect before the first submit (no replay)
        engine.start()
        val p = overlays.params(context.dp(Bubble.TAB_W_DP), context.dp(Bubble.TAB_H_DP)).apply {
            x = prefs.bubbleX; y = prefs.bubbleY
        }
        bubble.snap(p, capturer.width, capturer.height)  // tucked into the nearest screen edge
        bubble.params = p
        overlays.add(bubble, p)
    }

    fun onRotated() {
        if (!capturer.resize()) return  // night mode / font scale: same screen, keep Live and its translations
        // focusable panels sized for the old orientation would hide their buttons and block the game
        if (menu is LlmPanel) closeMenu()
        correctView?.let { overlays.remove(it); correctView = null; syncLivePause() }
        keepBubbleOnScreen()
        if (live.running) startLive()  // region pixels changed with the screen size
    }

    /** A position saved in portrait can be off a landscape screen: pull the bubble back inside. */
    private fun keepBubbleOnScreen() {
        val p = bubble.params ?: return
        val x = p.x
        val y = p.y
        bubble.snap(p, capturer.width, capturer.height)
        if (x != p.x || y != p.y) {
            if (bubble.isAttachedToWindow) overlays.update(bubble, p)
            bubble.invalidate()
        }
    }

    fun stop() {
        live.stop()
        (listOf(menu, layer, selector, correctView, bubble) + cards).forEach { overlays.remove(it) }
        cards.clear()
        engine.close()  // queued on the engine thread: ONNX sessions + ML Kit
        scope.cancel()
        capturer.release()
        engineThread.shutdown()
        ocrThread.shutdown()
    }

    // ---- menu -----------------------------------------------------------------------------------
    private fun panelState() = PanelState(TranslateMode.parse(prefs.translateMode), profile().scope == "screen", live.running)

    /** The bubble's panel: mode and scope toggles, "Chọn vùng…", one main button, "Thêm ▾" for the rest. */
    private fun showMenu() {
        closeMenu()
        lateinit var panel: ControlPanel
        panel = ControlPanel(
            context, panelState(),
            onMode = { mode ->
                if (panelState().onModeChanged(mode) == PanelEffect.STOP_LIVE) stopLive()
                prefs.translateMode = mode.key
                panel.render(panelState())
            },
            onScope = { screen ->
                val effect = panelState().onScopeChanged(screen)
                val p = profile()
                repo.save(p.copy(scope = if (screen) "screen" else "region"))
                if (effect == PanelEffect.RESTART_LIVE) { closeMenu(); startLive() } else panel.render(panelState())
            },
            onChooseRegion = { closeMenu(); chooseRegion(null) },
            onPrimary = { action ->
                closeMenu()
                when (action) {
                    PanelAction.TRANSLATE_REGION -> translateRegion()
                    PanelAction.TRANSLATE_SCREEN -> translateFullScreen()
                    PanelAction.START_LIVE -> startLive()
                    PanelAction.STOP_LIVE -> stopLive()
                }
            },
            extras = listOf(
                PanelTile("✍", "Sửa bản dịch", ::editLast),
                PanelTile("⚙", "Cài đặt", ::showSettings),
            ),
            onClose = ::closeMenu,
        )
        val bp = bubble.params ?: return
        panel.measure(View.MeasureSpec.UNSPECIFIED, View.MeasureSpec.UNSPECIFIED)
        val tabW = context.dp(Bubble.TAB_W_DP)
        val lp = overlays.params(WRAP_CONTENT, WRAP_CONTENT).apply {
            x = if (bp.x < capturer.width / 2) bp.x + tabW + context.dp(6)
            else (bp.x - panel.measuredWidth - context.dp(6)).coerceAtLeast(0)
            y = (bp.y + context.dp(Bubble.TAB_H_DP) / 2 - panel.measuredHeight / 2)
                .coerceIn(0, maxOf(0, capturer.height - panel.measuredHeight))
        }
        overlays.add(panel, lp)
        menu = panel
        syncLivePause()
    }

    private fun settingsValues() = SettingsValues(
        readable = profile().style == "classic", textScale = prefs.textScale,
        growLong = prefs.longText != "shrink", game = repo.label(gameId()),
    )

    /** ⚙ Cài đặt: style, text size, long translations, and the tools. */
    private fun showSettings() {
        closeMenu()
        lateinit var panel: SettingsPanel
        panel = SettingsPanel(
            context, settingsValues(),
            onReadable = { readable ->
                repo.save(profile().copy(style = if (readable) "classic" else "match"))
                restartLiveOnClose = true
                panel.render(settingsValues())
            },
            onScale = { up ->
                prefs.textScale = if (up) Layout.nextScale(prefs.textScale) else Layout.prevScale(prefs.textScale)
                restartLiveOnClose = true
                panel.render(settingsValues())
            },
            onGrowLong = { growLong ->
                prefs.longText = if (growLong) "grow" else "shrink"
                restartLiveOnClose = true
                panel.render(settingsValues())
            },
            tools = listOf(
                PanelTile("⊘", "Vùng bỏ qua", ::chooseIgnore),
                PanelTile("🎮", "Game: ${repo.label(gameId())}", ::showGameMenu),
                PanelTile("📷", "Kiểm tra chụp", ::probeCapture),
                PanelTile("📄", "Nhật ký Live", ::saveLiveLog),
                PanelTile("🌐", "Dịch bằng: ${dev.screentrans.core.llm.NAMES[profile().engine] ?: "máy"}", ::showLlm),
                PanelTile("📖", "Thuật ngữ", ::showTerms),
            ),
            onClose = ::closeMenu,
        )
        // a fixed width: measured "unspecified" the rows were narrow, laid out on screen they stretched past the edge
        val w = minOf(context.dp(460), (capturer.width * 0.9f).toInt())
        panel.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY), View.MeasureSpec.UNSPECIFIED)
        // at most 90% of the screen height: the sections scroll, the title and "Đóng" stay on screen
        val h = minOf(panel.measuredHeight, (capturer.height * 0.9f).toInt())
        val lp = overlays.params(w, h).apply {
            x = ((capturer.width - w) / 2).coerceAtLeast(0)
            y = ((capturer.height - h) / 2).coerceAtLeast(0)
        }
        overlays.add(panel, lp)
        menu = panel
        syncLivePause()
    }

    private val keyVault by lazy { dev.screentrans.engine.KeyVault(context) }

    /** 🌐 Dịch bằng: the game's engine (on-device or a remote LLM), key, model, limit, notes. */
    private fun showLlm() {
        closeMenu()
        val p = profile()
        val values = LlmValues(
            game = repo.label(p.id), engine = p.engine,
            savedKeys = dev.screentrans.core.llm.NAMES.keys.filter { keyVault.has(it) }.toSet(),
            models = prefs.llmModels, liveModels = prefs.llmLiveModels, kaggleUrl = prefs.kaggleUrl, dailyLimit = prefs.dailyLimit,
            usedToday = dev.screentrans.core.llm.UsageStore(java.io.File(context.filesDir, "llm")).used(),
            notes = p.llmNotes,
        )
        lateinit var panel: LlmPanel
        panel = LlmPanel(context, values, onSave = { e ->
            if (e.deleteKey) keyVault.set(e.engine, "")
            e.key?.let {  // encrypted (Android Keystore), never in prefs or logs
                if (!keyVault.set(e.engine, it)) android.widget.Toast.makeText(context, "Không lưu được key (Keystore lỗi).", android.widget.Toast.LENGTH_LONG).show()
            }
            if (e.engine in dev.screentrans.core.llm.NAMES) {
                prefs.llmModels = dev.screentrans.core.ui.LlmPrefsLogic.models(prefs.llmModels, e.engine, e.model)
                prefs.llmLiveModels = dev.screentrans.core.ui.LlmPrefsLogic.liveModels(prefs.llmLiveModels, e.engine, e.liveModel, prefs.llmModels)
            }
            if (e.engine == "kaggle") prefs.kaggleUrl = e.kaggleUrl
            prefs.dailyLimit = e.dailyLimit
            repo.save(profile(p.id).copy(engine = e.engine, llmNotes = e.notes))  // the game the panel showed
            engineGame = null  // send the game (with its engine) to the engine again
            useGame(profile())
            closeMenu()
        }, onClose = ::closeMenu)
        val w = (capturer.width * 0.9f).toInt()
        val h = (capturer.height * 0.85f).toInt()
        overlays.add(panel, overlays.params(w, h, focusable = true).apply {
            x = (capturer.width - w) / 2; y = (capturer.height - h) / 4
        })
        menu = panel
        syncLivePause()
    }

    /** 📖 Thuật ngữ: the game's own glossary terms; saved to its file and sent to the engine at once. */
    private fun showTerms() {
        closeMenu()
        val id = if (live.running) liveGame ?: gameId() else gameId()
        val file = repo.userGlossary(id)
        var rows = emptyList<screentrans.text.TermEdit.Row>()
        if (file.isFile) {
            val parsed = runCatching { screentrans.text.TermEdit.parse(file.readText()) }.getOrNull()
            if (parsed == null) {  // keep the broken file for the user, start a new one
                file.renameTo(java.io.File(file.path + ".bad"))
                android.widget.Toast.makeText(context, "File thuật ngữ hỏng, đã đổi tên thành ${file.name}.bad.", android.widget.Toast.LENGTH_LONG).show()
            } else rows = parsed
        }
        lateinit var panel: TermsPanel
        panel = TermsPanel(context, repo.label(id), rows, onSave = { edited ->
            repo.saveTerms(id, edited)
            engineGame = null  // reload the game's glossaries in the engine
            useGame(profile(id))
            closeMenu()
        }, onClose = ::closeMenu)
        val w = (capturer.width * 0.9f).toInt()
        val h = (capturer.height * 0.85f).toInt()
        overlays.add(panel, overlays.params(w, h, focusable = true).apply {
            x = (capturer.width - w) / 2; y = (capturer.height - h) / 4
        })
        menu = panel
        syncLivePause()
    }

    private fun stopLive() {
        live.stop()
        bubble.live = false
    }

    private fun closeMenu() {
        overlays.remove(menu)
        menu = null
        syncLivePause()
        if (restartLiveOnClose) {
            restartLiveOnClose = false
            if (live.running) startLive()
        }
    }

    private fun closeResults() {
        cards.forEach { overlays.remove(it) }
        cards.clear()
        overlays.remove(layer)
        layer = null
        syncLivePause()
    }

    /** Our menu and one-shot results are not hidden from Live frames: Live waits while they are shown. */
    private fun syncLivePause() {
        live.paused = menu != null || cards.isNotEmpty() || layer != null || selector != null || correctView != null
    }

    // ---- region ---------------------------------------------------------------------------------
    /** Edit the saved regions; [after] runs once regions were saved (none when cancelled / empty). */
    private fun chooseRegion(after: (() -> Unit)?) {
        closeResults()
        val wasLive = live.running
        stopLive()
        val p = profile()
        val view = RegionEditView(context, capturer.width, capturer.height, ProfileLogic.regionsOf(p)) { regions ->
            overlays.remove(selector)
            selector = null
            syncLivePause()
            if (regions != null) repo.save(ProfileLogic.withRegions(p, regions))
            when {
                regions != null && regions.isNotEmpty() && after != null -> after()
                wasLive -> startLive()
            }
        }
        overlays.add(view, overlays.params(MATCH_PARENT, MATCH_PARENT, focusable = true))
        selector = view
        syncLivePause()
    }

    /** Parts of the screen left out of Live's change detection (blinking arrow, animated HUD). */
    private fun chooseIgnore() {
        closeResults()
        val wasLive = live.running
        stopLive()
        val p = profile()
        val view = RegionEditView(context, capturer.width, capturer.height, ProfileLogic.ignoreOf(p)) { rects ->
            overlays.remove(selector)
            selector = null
            syncLivePause()
            if (rects != null) repo.save(ProfileLogic.withIgnore(p, rects))
            if (wasLive) startLive()
        }
        overlays.add(view, overlays.params(MATCH_PARENT, MATCH_PARENT, focusable = true))
        selector = view
        syncLivePause()
    }

    // ---- games ----------------------------------------------------------------------------------
    private fun gameId(): String = ProfileLogic.pickGame(detector.current(), prefs.manualGame, context.packageName)

    private fun profile(id: String = gameId()): Profile = repo.getOrDefault(id, repo.label(id))

    /** The engine translates with the game's glossary and the user's corrections for it. */
    private fun useGame(p: Profile) {
        if (engineGame == p.id) return
        engineGame = p.id
        val assets = context.assets
        val shipped = assets.list("glossary/games").orEmpty().sorted().map { name ->
            assets.open("glossary/games/$name").bufferedReader().readText()
        }
        val common = assets.open("glossary/common.json").bufferedReader().readText()
        val user = repo.userGlossary(p.id).takeIf { it.isFile }?.readText()
        val json = listOfNotNull(user) + shipped + common  // the user's terms win
        val llm = dev.screentrans.core.llm.LlmSettings(
            model = prefs.llmModels[p.engine] ?: "", url = if (p.engine == "kaggle") prefs.kaggleUrl else "",
            dailyLimit = prefs.dailyLimit, notes = p.llmNotes, liveModel = prefs.llmLiveModels[p.engine] ?: "",
        )
        engine.submit(EngineJob<Bitmap>(nextId++, fullScreen = false, image = null,
            control = EngineControl.SetGame(json, p.overrides, game = p.id, engine = p.engine, llm = llm)))
    }

    private fun showGameMenu() {
        val items = mutableListOf<Pair<String, () -> Unit>>()
        items += "Tự nhận game" to { prefs.manualGame = "" }
        if (!detector.hasAccess()) items += "Cho phép tự nhận game…" to {
            context.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        for (p in repo.all()) items += (p.name.ifEmpty { p.id }) to { prefs.manualGame = p.id }
        val panel = MenuPanel(context, items, onClose = ::closeMenu)
        val bp = bubble.params ?: return
        val lp = overlays.params(WRAP_CONTENT, WRAP_CONTENT).apply {
            x = if (bp.x < capturer.width / 2) bp.x + context.dp(52) else (bp.x - context.dp(220)).coerceAtLeast(0)
            y = bp.y
        }
        closeMenu()
        overlays.add(panel, lp)
        menu = panel
        syncLivePause()
    }

    /** One capture, one OCR, every saved region translated in one batch, one card per region. */
    private fun translateRegion() {
        val p = profile()
        val regions = ProfileLogic.regionsOf(p).filter { it.isUsable(capturer.width, capturer.height) }
        if (regions.isEmpty()) {
            chooseRegion(::translateRegion)
            return
        }
        useGame(p)
        scope.launch {
            val cap = captureWithoutOverlays() ?: return@launch showCard(null, "Không chụp được màn hình.", true)
            val frame = cap.frame
            val px = regions.map { rel ->
                val r = rel.toPx(frame.width, frame.height)
                Frames.clampRect(frame.width, frame.height, r[0], r[1], r[2], r[3])
            }.filter { it[2] - it[0] >= RelRect.MIN_PX && it[3] - it[1] >= RelRect.MIN_PX }
            if (px.isEmpty()) return@launch chooseRegion(::translateRegion)
            regionsPx = px
            regionJob = nextId++
            if (cap.looksBlack) maybeBlocked.add(regionJob)
            engine.submit(EngineJob(regionJob, fullScreen = false, image = frame, regions = px))
            when (val s = engine.state.value) {
                is EngineState.Failed -> showCard(px.first(), s.message, true)
                EngineState.Loading -> showCard(px.first(), "Đang tải model…")
                EngineState.Ready -> {
                    val id = regionJob
                    delay(300)
                    if (regionJob == id) showCard(px.first(), "Đang dịch…")
                }
            }
        }
    }

    private fun showRegionResults(segments: List<Segment>) {
        fun inside(seg: Segment, r: IntArray): Boolean {
            val cx = (seg.left + seg.right) / 2
            val cy = (seg.top + seg.bottom) / 2
            return cx >= r[0] && cx < r[2] && cy >= r[1] && cy < r[3]
        }
        lastSegments = segments
        var first = true
        for (r in regionsPx) {
            val mine = segments.filter { inside(it, r) }
            if (mine.isEmpty()) continue
            showCard(r, null, segments = mine, replace = first)
            first = false
        }
        if (first) showCard(regionsPx.firstOrNull(), null, segments = emptyList())  // no text anywhere
    }

    // ---- live -----------------------------------------------------------------------------------
    private fun toggleLive() {
        if (live.running) stopLive() else startLive()
    }

    private fun switchLiveScope() {
        val p = profile()
        repo.save(p.copy(scope = if (p.scope == "screen") "region" else "screen"))
        if (live.running) startLive()
    }


    private fun startLive() {
        closeResults()
        capturer.resize()
        val p = profile()
        useGame(p)
        liveGame = p.id
        val params = LiveParams(intervalMs = p.intervalMs, settleMs = p.settleMs,
            changeThreshold = p.changeThreshold.toFloat(), partialIntervalMs = 500)
        val ignorePx = ProfileLogic.ignoreOf(p).map { it.toPx(capturer.width, capturer.height) }
        if (p.scope == "screen") {
            live.start(listOf(intArrayOf(0, 0, capturer.width, capturer.height)), "screen", ignorePx, params, p.style,
                prefs.textScale, prefs.longText != "shrink")
            bubble.live = true
            return
        }
        val px = ProfileLogic.regionsOf(p).filter { it.isUsable(capturer.width, capturer.height) }.map { rel ->
            val r = rel.toPx(capturer.width, capturer.height)
            Frames.clampRect(capturer.width, capturer.height, r[0], r[1], r[2], r[3])
        }.filter { it[2] - it[0] >= RelRect.MIN_PX && it[3] - it[1] >= RelRect.MIN_PX }
        if (px.isEmpty()) {
            chooseRegion(::startLive)
            return
        }
        live.start(px, "region", ignorePx, params, p.style, prefs.textScale, prefs.longText != "shrink")
        bubble.live = true
    }

    // ---- corrections ----------------------------------------------------------------------------
    /** Common English words (names are not among them): term suggestions in the correction view. */
    private val commonWords: Set<String> by lazy {
        try {
            context.assets.open("glossary/common_words_en.txt").bufferedReader().readLines().map { it.trim().lowercase() }.toSet()
        } catch (e: Exception) {
            emptySet()
        }
    }

    /** Terms already in the game's own glossary (not suggested again). */
    private fun knownTerms(id: String): Set<String> = try {
        com.google.gson.JsonParser.parseString(repo.userGlossary(id).readText()).asJsonObject["entries"].asJsonArray
            .mapNotNull { it.asJsonObject["source"]?.asString }.toSet()
    } catch (e: Exception) {
        emptySet()
    }

    private fun editLast() {
        val segments = live.shownSegments().ifEmpty { lastSegments }
        openCorrect(segments)
    }

    private fun openCorrect(segments: List<Segment>) {
        if (segments.none { it.kind == Kind.TEXT && !it.translation.isNullOrEmpty() }) {
            showCard(null, "Chưa có bản dịch nào để sửa.")
            return
        }
        closeResults()
        overlays.remove(correctView)
        lateinit var v: CorrectView
        v = CorrectView(context, segments, commonWords, knownTerms(profile().id), onDone = { fixes, terms ->
            overlays.remove(v); correctView = null; syncLivePause()
            saveCorrections(fixes, terms)
        }, onCancel = { overlays.remove(v); correctView = null; syncLivePause() })
        val w = (capturer.width * 0.9f).toInt()
        val h = (capturer.height * 0.8f).toInt()
        overlays.add(v, overlays.params(w, h, focusable = true).apply {
            x = (capturer.width - w) / 2; y = (capturer.height - h) / 4
        })
        correctView = v
        syncLivePause()
    }

    private fun saveCorrections(fixes: List<Fix>, terms: List<Pair<String, String?>>) {
        if (fixes.isEmpty() && terms.isEmpty()) return
        val id = if (live.running) liveGame ?: gameId() else gameId()
        val p = profile(id)
        repo.save(p.copy(overrides = p.overrides + fixes.associate { normalizeText(it.source) to it.corrected }))
        if (terms.isNotEmpty()) repo.addTerms(id, terms)
        val model = engine.activeModelId.ifEmpty { AppEngine.MODEL_ID }  // the engine that translated (e.g. gemini:…)
        for (f in fixes) repo.logCorrection(id, model, f.source, f.machine, f.corrected)
        engine.submit(EngineJob<Bitmap>(nextId++, fullScreen = false, image = null,
            control = EngineControl.Correct(fixes.map { it.source to it.corrected }, terms)))
        fixes.forEach { live.applyCorrection(it.source, it.corrected) }
        val fixed = fixes.associate { it.source to it.corrected }
        lastSegments = lastSegments.map { s -> fixed[s.source]?.let { s.copy(translation = it) } ?: s }
        showCard(null, "Đã lưu ${fixes.size} câu sửa" + if (terms.isEmpty()) "." else " và ${terms.size} thuật ngữ.")
    }

    // ---- capture probe (debug) ------------------------------------------------------------------
    /** Draw a magenta square, capture, and report whether our overlays appear in the captured frames. */
    private fun probeCapture() {
        scope.launch {
            closeResults()
            live.setVisible(false)
            capturer.resize()
            val size = context.dp(120)
            val x = (capturer.width - size) / 2
            val y = (capturer.height - size) / 2
            val probe = View(context).apply { setBackgroundColor(Color.MAGENTA) }
            overlays.add(probe, overlays.params(size, size, touchable = false).apply { this.x = x; this.y = y })
            val shownAt = SystemClock.uptimeMillis()
            delay(400)
            val frame = capturer.capture(newerThan = shownAt)
            val frameAge = SystemClock.uptimeMillis() - capturer.lastFrameAt
            val frameNew = capturer.lastFrameAt > shownAt
            overlays.remove(probe)
            live.setVisible(true)
            if (frame == null) return@launch showCard(null, "Không chụp được màn hình.", true)
            val inset = size / 5  // look at the middle of the square only
            val l = (x + inset).coerceIn(0, frame.width - 1)
            val t = (y + inset).coerceIn(0, frame.height - 1)
            val w = minOf(size - 2 * inset, frame.width - l)
            val h = minOf(size - 2 * inset, frame.height - t)
            val pixels = IntArray(w * h)
            frame.getPixels(pixels, 0, w, l, t, w, h)
            val verdict = CaptureProbe.verdict(pixels, Color.MAGENTA)
            val what = when (verdict) {
                CaptureProbe.Verdict.OVERLAY_HIDDEN ->
                    "KHÔNG DÍNH: ảnh chụp không thấy ô hồng của app → bản dịch có thể đè lên chữ gốc mà không cần nháy."
                CaptureProbe.Verdict.OVERLAY_CAPTURED ->
                    "CÓ DÍNH: ảnh chụp thấy ô hồng của app → phải ẩn bản dịch khi chụp (nháy nhẹ)."
                CaptureProbe.Verdict.BLACK ->
                    "ẢNH ĐEN: chỗ ô hồng trong ảnh chụp bị đen (xem số liệu và ảnh đã lưu bên dưới)."
            }
            val small = Bitmap.createScaledBitmap(frame, 160, maxOf(1, 160 * frame.height / maxOf(1, frame.width)), false)
            val all = IntArray(small.width * small.height)
            small.getPixels(all, 0, small.width, 0, 0, small.width, small.height)
            val avg = pixels.fold(LongArray(3)) { acc, c ->
                acc[0] += (c shr 16) and 0xFF; acc[1] += (c shr 8) and 0xFF; acc[2] += c and 0xFF; acc
            }.map { it / maxOf(1, pixels.size) }
            val saved = saveProbe(frame)
            showCard(null, "Kiểm tra chụp màn hình\n$what\n\nAndroid ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), " +
                "${Build.MANUFACTURER} ${Build.MODEL}\nẢnh ${frame.width}×${frame.height}, màn hình ${capturer.width}×${capturer.height}\n" +
                "Cả ảnh đen: ${Frames.isMostlyBlack(all)} · màu giữa ô: rgb(${avg[0]}, ${avg[1]}, ${avg[2]})\n" +
                "Khung hình mới sau khi vẽ ô: $frameNew (cũ ${frameAge} ms)\n" +
                (saved?.let { "Đã lưu ảnh chụp: Ảnh › Pictures/ScreenTrans/$it" } ?: "Không lưu được ảnh chụp"))
        }
    }

    /** Save Live's event log to Download/ScreenTrans so the user can send it when something looks wrong. */
    private fun saveLiveLog() {
        val text = live.logText()
        if (text.isEmpty()) return showCard(null, "Chưa có nhật ký: bật Live trước.")
        scope.launch {
            val name = kotlinx.coroutines.withContext(Dispatchers.IO) {
                runCatching {
                    val name = "live-log-${System.currentTimeMillis()}.txt"
                    val values = ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                        put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
                        put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/ScreenTrans")
                    }
                    val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return@runCatching null
                    context.contentResolver.openOutputStream(uri)?.use { it.write(text.toByteArray()) } ?: return@runCatching null
                    name
                }.getOrNull()
            }
            showCard(null, if (name != null) "Đã lưu: Download/ScreenTrans/$name" else "Không lưu được nhật ký.", name == null)
        }
    }

    /** Save the probe frame to Pictures/ScreenTrans so the user can share what the app really captured. */
    private suspend fun saveProbe(frame: Bitmap): String? = kotlinx.coroutines.withContext(Dispatchers.IO) {
        runCatching {
            val name = "probe-${System.currentTimeMillis()}.png"
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/ScreenTrans")
            }
            val resolver = context.contentResolver
            val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return@runCatching null
            resolver.openOutputStream(uri)?.use { frame.compress(Bitmap.CompressFormat.PNG, 100, it) } ?: return@runCatching null
            name
        }.getOrNull()
    }

    // ---- full screen ----------------------------------------------------------------------------
    private fun translateFullScreen() {
        useGame(profile())
        scope.launch {
            val cap = captureWithoutOverlays() ?: return@launch showCard(null, "Không chụp được màn hình.", true)
            val frame = cap.frame
            fullJob = nextId++
            if (cap.looksBlack) maybeBlocked.add(fullJob)
            val l = FullScreenLayer(context, onBlockTapped = ::showDetail, onClose = ::closeResults)
            overlays.add(l, overlays.params(MATCH_PARENT, MATCH_PARENT))
            layer = l
            syncLivePause()
            (engine.state.value as? EngineState.Failed)?.let { l.finish(); showCard(null, it.message, true) }
            engine.submit(EngineJob(fullJob, fullScreen = true, image = frame))
        }
    }

    private fun showDetail(seg: Segment) {
        val r = intArrayOf(seg.left.toInt(), seg.top.toInt(), seg.right.toInt(), seg.bottom.toInt())
        showCard(r, null, false, listOf(seg), showSource = true)
    }

    // ---- capture --------------------------------------------------------------------------------
    /** Hide our own windows, wait for a frame without them, capture, show them again. */
    private class Captured(val frame: Bitmap, val looksBlack: Boolean)

    private suspend fun captureWithoutOverlays(): Captured? {
        closeMenu()
        closeResults()
        live.setVisible(false)
        capturer.resize()  // the rotation callback may not fire while our activity sits in the background
        keepBubbleOnScreen()
        bubble.visibility = View.INVISIBLE
        val hiddenAt = SystemClock.uptimeMillis()
        delay(50)
        val frame = capturer.capture(newerThan = hiddenAt)
        bubble.visibility = View.VISIBLE
        live.setVisible(true)
        if (frame == null) return null
        val small = Bitmap.createScaledBitmap(frame, 160, maxOf(1, 160 * frame.height / maxOf(1, frame.width)), false)
        val pixels = IntArray(small.width * small.height)
        small.getPixels(pixels, 0, small.width, 0, 0, small.width, small.height)
        // A black-looking frame may still be a dark scene with thin text: OCR decides (see onEvent).
        return Captured(frame, Frames.isMostlyBlack(pixels))
    }

    // ---- results --------------------------------------------------------------------------------
    private fun showCard(
        region: IntArray?, message: String?, error: Boolean = false,
        segments: List<Segment>? = null, showSource: Boolean = false, replace: Boolean = true,
    ) {
        if (replace) closeCards()
        lateinit var c: ResultCard
        c = ResultCard(context, onClose = { overlays.remove(c); cards.remove(c); syncLivePause() },
            onEdit = if (segments.isNullOrEmpty()) null else { segs -> openCorrect(segs) })
        if (segments != null) c.showSegments(segments, showSource) else c.showMessage(message ?: "", error)
        val maxW = (capturer.width * 0.9f).toInt()
        val maxH = (capturer.height * 0.8f).toInt()  // long text scrolls inside the card
        val width = if (region == null) maxW else minOf(maxW, maxOf(region[2] - region[0], context.dp(280)))
        c.measure(
            View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(maxH, View.MeasureSpec.AT_MOST),
        )
        val reg = region ?: intArrayOf(
            (capturer.width - width) / 2, capturer.height / 3, (capturer.width + width) / 2, capturer.height / 3,
        )
        val pos = Layout.placeOverlay(reg, width, c.measuredHeight, capturer.width, capturer.height)
        val p = overlays.params(width, minOf(c.measuredHeight, maxH)).apply { x = pos[0]; y = pos[1] }
        overlays.add(c, p)
        cards.add(c)
        syncLivePause()
    }

    private fun closeCards() {
        cards.forEach { overlays.remove(it) }
        cards.clear()
        syncLivePause()
    }

    private fun onEvent(e: EngineEvent) {
        when (e) {
            is EngineEvent.SegmentReady -> if (e.jobId == fullJob) layer?.add(e.segment)
            is EngineEvent.Done -> {
                val blocked = Frames.reportBlocked(
                    mostlyBlack = maybeBlocked.remove(e.jobId), textFound = e.segments.any { it.kind == Kind.TEXT },
                )
                when (e.jobId) {
                    regionJob -> {
                        regionJob = -1
                        if (blocked) showCard(regionsPx.firstOrNull(), BLOCKED, true) else showRegionResults(e.segments)
                    }
                    fullJob -> {
                        fullJob = -1
                        lastSegments = e.segments
                        layer?.finish()
                        if (blocked) showCard(null, BLOCKED, true)
                    }
                }
            }
            is EngineEvent.JobFailed -> when {
                e.why == SUPERSEDED -> Unit
                e.jobId == regionJob -> { regionJob = -1; showCard(regionsPx.firstOrNull(), e.why, true) }
                e.jobId == fullJob -> { fullJob = -1; layer?.finish(); showCard(null, e.why, true) }
            }
            is EngineEvent.Notice -> android.widget.Toast.makeText(context, e.message, android.widget.Toast.LENGTH_LONG).show()
            else -> Unit  // live events: LiveController collects them

        }
    }
}
