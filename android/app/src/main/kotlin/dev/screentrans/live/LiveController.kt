package dev.screentrans.live

import android.content.Context
import android.graphics.Bitmap
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import dev.screentrans.capture.ScreenCapturer
import dev.screentrans.core.EngineEvent
import dev.screentrans.core.EngineJob
import dev.screentrans.core.Layout
import dev.screentrans.core.TranslationEngine
import dev.screentrans.core.live.LiveHost
import dev.screentrans.core.live.LiveParams
import dev.screentrans.core.live.LiveSession
import dev.screentrans.core.live.Thumb
import dev.screentrans.ui.Overlays
import dev.screentrans.ui.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import screentrans.text.Paragraph
import screentrans.text.Segment

/**
 * Android Live: every tick compares small gray thumbnails of the watched regions (read straight from
 * the held frame), feeds [LiveSession], and draws results. Dialogue cards sit outside the regions;
 * the large-area layer is hidden while the OCR frame is captured, and its own redraws are ignored.
 * Main thread only.
 */
class LiveController(
    private val context: Context,
    private val scope: CoroutineScope,
    private val capturer: ScreenCapturer,
    private val engine: TranslationEngine<Bitmap>,
    private val overlays: Overlays,
    private val newId: () -> Int,
    /** Hide / show our other windows (the bubble) around an OCR capture in large-area mode. */
    private val hideOthers: (Boolean) -> Unit,
) : LiveHost {
    private var session: LiveSession? = null
    private var loop: Job? = null
    private var events: Job? = null
    private var regions: List<IntArray> = emptyList()
    private var prev: Array<FloatArray?> = emptyArray()
    private val cards = HashMap<Int, LiveCard>()
    private var areaLayer: LiveAreaLayer? = null
    private var capturing = false
    private var startedAt = 0L

    /** Our menu / one-shot results are on screen: they would end up in the Live frames, so wait. */
    var paused = false
        set(value) {
            if (field == value) return
            field = value
            if (!value) {
                resetReference()
                session?.overlayChanged()
            }
        }

    val running: Boolean get() = session?.running == true

    private fun now(): Int = (SystemClock.uptimeMillis() - startedAt).toInt()

    fun start(regionsPx: List<IntArray>, area: Boolean) {
        stop()
        regions = regionsPx
        prev = arrayOfNulls(regionsPx.size)
        startedAt = SystemClock.uptimeMillis()
        val s = LiveSession(LiveParams(), area, host = this)
        session = s
        if (area) {
            val layer = LiveAreaLayer(context)
            overlays.add(layer, overlays.params(MATCH_PARENT, MATCH_PARENT, touchable = false))
            areaLayer = layer
        }
        events = scope.launch { engine.events.collect(::onEvent) }
        loop = scope.launch {
            while (isActive && s.running) {
                if (!capturing && !paused) tick(s)
                delay(s.nextDelayMs().toLong())
            }
        }
    }

    fun stop() {
        session?.stop()
        session = null
        loop?.cancel()
        events?.cancel()
        loop = null
        events = null
        cards.values.forEach { overlays.remove(it) }
        cards.clear()
        overlays.remove(areaLayer)
        areaLayer = null
        capturing = false
    }

    /** One-shot translations hide Live windows so they are not captured. */
    fun setVisible(visible: Boolean) {
        setLiveWindows(if (visible) View.VISIBLE else View.INVISIBLE)
        if (visible) resetReference()
    }

    private fun setLiveWindows(v: Int) {
        cards.values.forEach { it.visibility = v }
        areaLayer?.visibility = v
    }

    private fun resetReference() {
        prev = arrayOfNulls(regions.size)
    }

    private fun tick(s: LiveSession) {
        var worst = 0f
        var any = false
        regions.forEachIndexed { i, r ->
            val thumb = capturer.thumbnail(r) ?: return@forEachIndexed
            any = true
            prev[i]?.let { worst = maxOf(worst, Thumb.diff(it, thumb)) }
            prev[i] = thumb
        }
        if (any) s.onFrame(now(), worst)
    }

    // ---- LiveHost -----------------------------------------------------------------------------------
    override fun requestOcr(): Int {
        val id = newId()
        val s = session ?: return id
        scope.launch {
            // Android cannot exclude our windows from the capture: hide them (layer, cards, bubble).
            capturing = true
            setLiveWindows(View.INVISIBLE)
            hideOthers(true)
            val hiddenAt = SystemClock.uptimeMillis()
            delay(50)
            val frame = capturer.capture(newerThan = hiddenAt)
            hideOthers(false)
            if (session === s) {
                setLiveWindows(View.VISIBLE)
                delay(120)  // let a frame with our windows back arrive: it becomes the new reference
            }
            if (session !== s) return@launch  // stopped / restarted meanwhile: leave the new session alone
            resetReference()
            s.overlayChanged()
            capturing = false
            if (frame == null || !s.running) {
                s.onJobFailed(id)
                return@launch
            }
            engine.submit(EngineJob(id, fullScreen = false, image = frame, regions = regions, liveOcr = true))
        }
        return id
    }

    override fun requestTranslate(paragraphs: List<List<Paragraph>>): Int {
        val id = newId()
        engine.submit(EngineJob<Bitmap>(id, fullScreen = false, image = null, liveParagraphs = paragraphs))
        return id
    }

    override fun showDialogue(segments: List<List<Segment>>) {
        segments.forEachIndexed { i, segs ->
            val region = regions.getOrNull(i) ?: return@forEachIndexed
            if (segs.isEmpty()) {
                overlays.remove(cards.remove(i))
                return@forEachIndexed
            }
            val card = cards.getOrPut(i) { LiveCard(context) }
            card.show(segs)
            val maxW = (capturer.width * 0.9f).toInt()
            val width = minOf(maxW, maxOf(region[2] - region[0], context.dp(240)))
            card.measure(
                View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec((capturer.height * 0.5f).toInt(), View.MeasureSpec.AT_MOST),
            )
            // Outside every watched region; if that is impossible it may overlap, and it is hidden
            // for each OCR capture anyway (requestOcr).
            val pos = Layout.placeOutside(region, width, card.measuredHeight, capturer.width, capturer.height, regions)
                ?: Layout.placeOverlay(region, width, card.measuredHeight, capturer.width, capturer.height)
            val p = overlays.params(width, WRAP_CONTENT, touchable = false).apply { x = pos[0]; y = pos[1] }
            if (overlays.isAdded(card)) overlays.update(card, p) else overlays.add(card, p)
        }
    }

    override fun setBlock(key: String, segment: Segment) {
        areaLayer?.set(key, segment)
    }

    override fun removeBlock(key: String) {
        areaLayer?.remove(key)
    }

    private fun onEvent(e: EngineEvent) {
        val s = session ?: return
        when (e) {
            is EngineEvent.OcrDone -> s.onOcrDone(e.jobId, e.paragraphs, now())
            is EngineEvent.Partial -> s.onPartial(e.jobId, e.segments)
            is EngineEvent.Done -> s.onJobEnded(e.jobId)
            is EngineEvent.JobFailed -> s.onJobFailed(e.jobId)
            is EngineEvent.SegmentReady -> Unit
        }
    }
}
