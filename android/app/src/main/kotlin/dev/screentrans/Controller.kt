package dev.screentrans

import android.content.Context
import android.graphics.Bitmap
import android.media.projection.MediaProjection
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowManager
import dev.screentrans.capture.ScreenCapturer
import dev.screentrans.core.EngineEvent
import dev.screentrans.core.EngineJob
import dev.screentrans.core.EngineState
import dev.screentrans.core.Frames
import dev.screentrans.core.Layout
import dev.screentrans.core.RelRect
import dev.screentrans.core.SUPERSEDED
import dev.screentrans.core.TranslationEngine
import dev.screentrans.engine.AppEngine
import dev.screentrans.ui.Bubble
import dev.screentrans.ui.FullScreenLayer
import dev.screentrans.ui.MenuPanel
import dev.screentrans.ui.Overlays
import dev.screentrans.ui.Prefs
import dev.screentrans.ui.RegionSelectView
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
    private val engine = TranslationEngine({ AppEngine.bundle(context) }, scope, engineThread.asCoroutineDispatcher())

    private val bubble = Bubble(context, onTap = ::showMenu, onMoved = { x, y -> prefs.bubbleX = x; prefs.bubbleY = y })
    private var menu: MenuPanel? = null
    private var card: ResultCard? = null
    private var layer: FullScreenLayer? = null
    private var selector: View? = null
    private var nextId = 1
    private var regionJob = -1
    private var regionPx = intArrayOf(0, 0, 0, 0)
    private var fullJob = -1
    private val maybeBlocked = HashSet<Int>()  // jobs whose frame looked black (FLAG_SECURE?)

    fun start() {
        scope.launch { engine.events.collect(::onEvent) }  // collect before the first submit (no replay)
        engine.start()
        val size = context.dp(48)
        val pos = Layout.clampBubble(prefs.bubbleX, prefs.bubbleY, size, capturer.width, capturer.height)
        val p = overlays.params(size, size).apply { x = pos[0]; y = pos[1] }
        bubble.params = p
        overlays.add(bubble, p)
    }

    fun onRotated() {
        capturer.resize()
        keepBubbleOnScreen()
    }

    /** A position saved in portrait can be off a landscape screen: pull the bubble back inside. */
    private fun keepBubbleOnScreen() {
        val p = bubble.params ?: return
        val pos = Layout.clampBubble(p.x, p.y, context.dp(48), capturer.width, capturer.height)
        if (pos[0] != p.x || pos[1] != p.y) {
            p.x = pos[0]; p.y = pos[1]
            if (bubble.isAttachedToWindow) overlays.update(bubble, p)
        }
    }

    fun stop() {
        listOf(menu, card, layer, selector, bubble).forEach { overlays.remove(it) }
        engine.close()  // queued on the engine thread: ONNX sessions + ML Kit
        scope.cancel()
        capturer.release()
        engineThread.shutdown()
    }

    // ---- menu -----------------------------------------------------------------------------------
    private fun showMenu() {
        closeMenu()
        val panel = MenuPanel(context, listOf(
            "Dịch vùng" to ::translateRegion,
            "Toàn màn hình" to ::translateFullScreen,
            "Chọn vùng mới" to { chooseRegion(translateAfter = false) },
        ), onClose = ::closeMenu)
        val bp = bubble.params ?: return
        val p = overlays.params(WRAP_CONTENT, WRAP_CONTENT).apply {
            x = if (bp.x < capturer.width / 2) bp.x + context.dp(52) else (bp.x - context.dp(180)).coerceAtLeast(0)
            y = bp.y
        }
        overlays.add(panel, p)
        menu = panel
    }

    private fun closeMenu() {
        overlays.remove(menu)
        menu = null
    }

    private fun closeResults() {
        overlays.remove(card)
        card = null
        overlays.remove(layer)
        layer = null
    }

    // ---- region ---------------------------------------------------------------------------------
    private fun chooseRegion(translateAfter: Boolean) {
        closeResults()
        val view = RegionSelectView(context, capturer.width, capturer.height) { rel ->
            overlays.remove(selector)
            selector = null
            if (rel != null) {
                prefs.region = rel
                if (translateAfter) translateRegion()
            }
        }
        overlays.add(view, overlays.params(MATCH_PARENT, MATCH_PARENT, focusable = true))
        selector = view
    }

    private fun translateRegion() {
        val rel = prefs.region
        if (rel == null || !rel.isUsable(capturer.width, capturer.height)) {
            chooseRegion(translateAfter = true)
            return
        }
        scope.launch {
            val cap = captureWithoutOverlays() ?: return@launch showCard(null, "Không chụp được màn hình.", true)
            val frame = cap.frame
            val px = rel.toPx(frame.width, frame.height)
            val r = Frames.clampRect(frame.width, frame.height, px[0], px[1], px[2], px[3])
            if (r[2] - r[0] < RelRect.MIN_PX || r[3] - r[1] < RelRect.MIN_PX) return@launch chooseRegion(true)
            val crop = Bitmap.createBitmap(frame, r[0], r[1], r[2] - r[0], r[3] - r[1])
            regionPx = r
            regionJob = nextId++
            if (cap.looksBlack) maybeBlocked.add(regionJob)
            engine.submit(EngineJob(regionJob, fullScreen = false, image = crop))
            when (val s = engine.state.value) {
                is EngineState.Failed -> showCard(r, s.message, true)
                EngineState.Loading -> showCard(r, "Đang tải model…")
                EngineState.Ready -> {
                    val id = regionJob
                    delay(300)
                    if (regionJob == id) showCard(r, "Đang dịch…")
                }
            }
        }
    }

    // ---- full screen ----------------------------------------------------------------------------
    private fun translateFullScreen() {
        scope.launch {
            val cap = captureWithoutOverlays() ?: return@launch showCard(null, "Không chụp được màn hình.", true)
            val frame = cap.frame
            fullJob = nextId++
            if (cap.looksBlack) maybeBlocked.add(fullJob)
            val l = FullScreenLayer(context, onBlockTapped = ::showDetail, onClose = ::closeResults)
            overlays.add(l, overlays.params(MATCH_PARENT, MATCH_PARENT))
            layer = l
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
        capturer.resize()  // the rotation callback may not fire while our activity sits in the background
        keepBubbleOnScreen()
        bubble.visibility = View.INVISIBLE
        val hiddenAt = SystemClock.uptimeMillis()
        delay(50)
        val frame = capturer.capture(newerThan = hiddenAt)
        bubble.visibility = View.VISIBLE
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
        segments: List<Segment>? = null, showSource: Boolean = false,
    ) {
        overlays.remove(card)
        val c = ResultCard(context) { overlays.remove(card); card = null }
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
        card = c
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
                        if (blocked) showCard(regionPx, BLOCKED, true) else showCard(regionPx, null, segments = e.segments)
                    }
                    fullJob -> {
                        fullJob = -1
                        layer?.finish()
                        if (blocked) showCard(null, BLOCKED, true)
                    }
                }
            }
            is EngineEvent.JobFailed -> when {
                e.why == SUPERSEDED -> Unit
                e.jobId == regionJob -> { regionJob = -1; showCard(regionPx, e.why, true) }
                e.jobId == fullJob -> { fullJob = -1; layer?.finish(); showCard(null, e.why, true) }
            }
        }
    }
}
