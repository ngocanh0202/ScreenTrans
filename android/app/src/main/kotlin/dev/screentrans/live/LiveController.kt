package dev.screentrans.live

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import dev.screentrans.capture.ScreenCapturer
import dev.screentrans.core.CaptureProbe
import dev.screentrans.core.EngineEvent
import dev.screentrans.core.EngineJob
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
import screentrans.text.Kind
import screentrans.text.Paragraph
import screentrans.text.Segment

/**
 * Android Live (4b): every tick compares small gray thumbnails of the watched regions (read straight
 * from the held frame) and feeds [LiveSession]; translations are drawn over each text block, sentence by
 * sentence. Once per capture session a probe checks whether our overlays end up in the frames:
 * single-app capture (Android 14+) → no; full-screen capture → yes, then the layer is hidden for each
 * OCR capture and our own redraws are ignored. Main thread only.
 */
class LiveController(
    private val context: Context,
    private val scope: CoroutineScope,
    private val capturer: ScreenCapturer,
    private val engine: TranslationEngine<Bitmap>,
    private val overlays: Overlays,
    private val newId: () -> Int,
    /** Show a message to the user (a result card). */
    private val notify: (String) -> Unit,
    /** Hide / show our other windows (the bubble) around an OCR capture when overlays are captured. */
    private val hideOthers: (Boolean) -> Unit,
) : LiveHost {
    enum class CaptureMode { UNKNOWN, HIDDEN, CAPTURED }

    var captureMode = CaptureMode.UNKNOWN
        private set
    private var session: LiveSession? = null
    private var loop: Job? = null
    private var events: Job? = null
    private var ocrCapture: Job? = null
    private var regions: List<IntArray> = emptyList()
    private var prev: Array<FloatArray?> = emptyArray()
    private var layer: LiveAreaLayer? = null
    private var capturing = false
    private var startedAt = 0L
    private var hintShown = false

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

    /** Translations shown last (for "edit the last translation"). */
    val lastSegments: List<Segment> get() = session?.lastSegments.orEmpty()

    private fun now(): Int = (SystemClock.uptimeMillis() - startedAt).toInt()

    /** [scopeName]: "screen" ([regionsPx] = the whole screen) or "region". */
    fun start(regionsPx: List<IntArray>, scopeName: String) {
        stop()
        regions = regionsPx
        prev = arrayOfNulls(regionsPx.size)
        startedAt = SystemClock.uptimeMillis()
        val s = LiveSession(LiveParams(partialIntervalMs = 500), scopeName, regionsPx.size, host = this)
        session = s
        val l = LiveAreaLayer(context)
        overlays.add(l, overlays.params(MATCH_PARENT, MATCH_PARENT, touchable = false))
        layer = l
        events = scope.launch { engine.events.collect(::onEvent) }
        loop = scope.launch {
            if (captureMode == CaptureMode.UNKNOWN) probe()
            s.overlaysInCapture = captureMode == CaptureMode.CAPTURED
            if (s.overlaysInCapture && !hintShown) {
                hintShown = true
                notify("Bản dịch Live sẽ nháy nhẹ khi chụp. Để hết nháy: Dừng ScreenTrans, bật lại và chọn " +
                    "\"Một ứng dụng\" → game khi Android hỏi quyền ghi màn hình.")
            }
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
        ocrCapture?.cancel()
        loop = null
        events = null
        ocrCapture = null
        overlays.remove(layer)
        layer = null
        if (capturing) hideOthers(false)
        capturing = false
    }

    /** One-shot translations hide Live windows so they are not captured. */
    fun setVisible(visible: Boolean) {
        layer?.visibility = if (visible) View.VISIBLE else View.INVISIBLE
        if (visible) resetReference()
    }

    private fun resetReference() {
        prev = arrayOfNulls(regions.size)
    }

    /** Draw a small magenta square in a corner, capture, and see whether it shows up in the frame. */
    private suspend fun probe() {
        val size = context.dp(24)
        val x = capturer.width - size - context.dp(8)
        val y = context.dp(8)
        val v = View(context).apply { setBackgroundColor(Color.MAGENTA) }
        overlays.add(v, overlays.params(size, size, touchable = false).apply { this.x = x; this.y = y })
        val shownAt = SystemClock.uptimeMillis()
        delay(300)
        val frame = capturer.capture(newerThan = shownAt)
        overlays.remove(v)
        if (frame == null) return  // try again next time Live starts
        val inset = size / 4
        val w = (size - 2 * inset).coerceAtMost(frame.width - x - inset).coerceAtLeast(1)
        val h = (size - 2 * inset).coerceAtMost(frame.height - y - inset).coerceAtLeast(1)
        val px = IntArray(w * h)
        frame.getPixels(px, 0, w, (x + inset).coerceIn(0, frame.width - 1), (y + inset).coerceIn(0, frame.height - 1), w, h)
        captureMode = when (CaptureProbe.verdict(px, Color.MAGENTA)) {
            CaptureProbe.Verdict.OVERLAY_CAPTURED -> CaptureMode.CAPTURED
            CaptureProbe.Verdict.OVERLAY_HIDDEN -> CaptureMode.HIDDEN
            CaptureProbe.Verdict.BLACK -> CaptureMode.UNKNOWN  // chosen app not on screen yet: decide later
        }
        resetReference()
    }

    private fun tick(s: LiveSession) {
        var worst = 0f
        var any = false
        regions.forEachIndexed { i, r ->
            val thumb = capturer.thumbnail(r) ?: return@forEachIndexed
            if (thumb.average() < 2.0) return@forEachIndexed  // black: the captured app is not on screen
            any = true
            prev[i]?.let { worst = maxOf(worst, Thumb.diff(it, thumb)) }
            prev[i] = thumb
        }
        if (any) s.onFrame(now(), worst)
    }

    // ---- LiveHost -----------------------------------------------------------------------------------
    override fun requestOcr(final: Boolean): Int {
        val id = newId()
        val s = session ?: return id
        ocrCapture = scope.launch {
            val frame = if (s.overlaysInCapture) {
                capturing = true
                layer?.visibility = View.INVISIBLE
                hideOthers(true)
                val hiddenAt = SystemClock.uptimeMillis()
                delay(50)
                val f = capturer.capture(newerThan = hiddenAt)
                hideOthers(false)
                if (session === s) {
                    layer?.visibility = View.VISIBLE
                    delay(120)  // let a frame with our layer back arrive: it becomes the new reference
                    resetReference()
                    s.overlayChanged()
                }
                capturing = false
                f
            } else {
                capturer.capture()
            }
            if (session !== s) return@launch
            if (frame == null) {
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

    override fun setBlock(region: Int, key: String, text: String, box: FloatArray, kind: Kind) {
        layer?.set("$region:$key", text, box, kind)
    }

    override fun removeBlock(region: Int, key: String) {
        layer?.remove("$region:$key")
    }

    private fun onEvent(e: EngineEvent) {
        val s = session ?: return
        when (e) {
            is EngineEvent.OcrDone -> s.onOcrDone(e.jobId, e.paragraphs)
            is EngineEvent.Partial -> s.onPartial(e.jobId, e.segments)
            is EngineEvent.Done -> s.onJobEnded(e.jobId)
            is EngineEvent.JobFailed -> s.onJobFailed(e.jobId)
            is EngineEvent.SegmentReady -> Unit
        }
    }
}
