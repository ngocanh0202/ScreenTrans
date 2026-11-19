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
import dev.screentrans.core.SUPERSEDED
import dev.screentrans.core.TranslationEngine
import dev.screentrans.core.live.BlockStyle
import dev.screentrans.core.live.LiveHost
import dev.screentrans.core.live.LiveParams
import dev.screentrans.core.live.LiveSession
import dev.screentrans.core.live.Thumb
import dev.screentrans.core.profile.ProfileLogic
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

    private companion object {
        const val THUMB_W = 64
    }

    var captureMode = CaptureMode.UNKNOWN
        private set
    private var session: LiveSession? = null
    private var loop: Job? = null
    private var events: Job? = null
    private var ocrCapture: Job? = null
    private var regions: List<IntArray> = emptyList()
    private var prev: Array<FloatArray?> = emptyArray()
    private var ignore: List<IntArray> = emptyList()
    private var masks: Array<BooleanArray?> = emptyArray()
    private var style = "match"
    private val frames = HashMap<Int, Bitmap>()      // OCR job -> the frame it reads (to sample colours)
    private var lastOcrFrame: Bitmap? = null
    private val styles = HashMap<String, BlockStyle?>()  // block -> sampled colours (null: readable style)
    private var blackTicks = 0
    private var blackReported = false
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

    // ---- debug log (bubble menu "Lưu nhật ký Live") ----------------------------------------------------
    private val logLines = ArrayDeque<String>()

    private fun log(line: String) {
        val t = (SystemClock.uptimeMillis() - startedAt) / 1000.0
        logLines.addLast("%8.2f  %s".format(t, line))
        while (logLines.size > 400) logLines.removeFirst()
    }

    /** The last 400 Live events (OCR text, translation requests and results, failures). */
    fun logText(): String = logLines.joinToString("\n")

    /** Every translated sentence Live shows now (for "edit the last translation"). */
    fun shownSegments(): List<Segment> = session?.shownSegments().orEmpty()

    fun applyCorrection(source: String, corrected: String) {
        session?.applyCorrection(source, corrected)
    }

    private fun now(): Int = (SystemClock.uptimeMillis() - startedAt).toInt()

    /**
     * [scopeName]: "screen" ([regionsPx] = the whole screen) or "region"; [ignorePx]: parts left out of the
     * change detection (blinking arrow, animated HUD); [params]: from the game profile.
     */
    fun start(regionsPx: List<IntArray>, scopeName: String, ignorePx: List<IntArray> = emptyList(),
              params: LiveParams = LiveParams(partialIntervalMs = 500), styleName: String = "match") {
        stop()
        style = styleName
        regions = regionsPx
        ignore = ignorePx
        prev = arrayOfNulls(regionsPx.size)
        masks = arrayOfNulls(regionsPx.size)
        blackTicks = 0
        blackReported = false
        startedAt = SystemClock.uptimeMillis()
        val s = LiveSession(params, scopeName, regionsPx.size, host = this)
        session = s
        val l = LiveAreaLayer(context)
        overlays.add(l, overlays.params(MATCH_PARENT, MATCH_PARENT, touchable = false))
        layer = l
        events = scope.launch { engine.events.collect(::onEvent) }
        loop = scope.launch {
            if (captureMode == CaptureMode.UNKNOWN) probe()
            // Unknown (the probe saw no frame): hide while capturing, never OCR our own translations.
            s.overlaysInCapture = captureMode != CaptureMode.HIDDEN
            log("start scope=$scopeName style=$styleName capture=$captureMode regions=${regions.size} ignore=${ignore.size}")
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
        frames.clear()
        styles.clear()
        lastOcrFrame = null
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
        val thumbs = regions.map { capturer.thumbnail(it) }
        if (thumbs.all { it == null }) return  // no frame yet
        if (thumbs.all { it == null || it.average() < 2.0 }) {
            // Only a black WHOLE frame means the game is not visible (an empty dark dialogue box is fine).
            val whole = capturer.thumbnail(intArrayOf(0, 0, capturer.width, capturer.height)) ?: return
            if (whole.average() < 2.0) {
                if (++blackTicks >= 10 && !blackReported) {  // ~3 s of black frames
                    blackReported = true
                    notify("Không thấy hình game (game chặn chụp màn hình, hoặc bạn đang ở ứng dụng khác) — Live chờ tới khi thấy lại hình.")
                }
                return
            }
        }
        blackTicks = 0
        blackReported = false
        var worst = 0f
        thumbs.forEachIndexed { i, thumb ->
            if (thumb == null) return@forEachIndexed
            prev[i]?.let { worst = maxOf(worst, Thumb.diff(it, thumb, mask(i, regions[i], thumb.size))) }
            prev[i] = thumb
        }
        s.onFrame(now(), worst)
    }

    /** Thumbnails are THUMB_W wide (narrower regions are rare: no mask then). */
    private fun mask(i: Int, region: IntArray, size: Int): BooleanArray? {
        if (ignore.isEmpty() || size % THUMB_W != 0) return null
        val m = masks[i]
        if (m != null && m.size == size) return m
        return ProfileLogic.ignoreMask(region, ignore, THUMB_W, size / THUMB_W).also { masks[i] = it }
    }

    // ---- LiveHost -----------------------------------------------------------------------------------
    override fun requestOcr(final: Boolean): Int {
        val id = newId()
        log("request ocr $id final=$final")
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
            frames[id] = frame
            engine.submit(EngineJob(id, fullScreen = false, image = frame, regions = regions, liveOcr = true))
        }
        return id
    }

    override fun requestTranslate(paragraphs: List<List<Paragraph>>): Int {
        val id = newId()
        log("translate $id: " + paragraphs.flatten().joinToString(" | ") { "\"${it.text}\"" })
        engine.submit(EngineJob<Bitmap>(id, fullScreen = false, image = null, liveParagraphs = paragraphs))
        return id
    }

    override fun setBlock(region: Int, key: String, text: String, box: FloatArray, kind: Kind, lineHeight: Float) {
        val k = "$region:$key"
        val colors = if (style != "match") null else styles.getOrPut(k) { sampleStyle(box) }
        layer?.set(k, text, box, kind, BlockStyle.fontPxFor(lineHeight), colors)
    }

    /** Colours of the source text block, from the frame its OCR read (null: readable white on dark). */
    private fun sampleStyle(box: FloatArray): BlockStyle? {
        val f = lastOcrFrame ?: return null
        val l = box[0].toInt().coerceIn(0, f.width - 1)
        val t = box[1].toInt().coerceIn(0, f.height - 1)
        val w = (box[2].toInt() - l).coerceIn(1, f.width - l)
        val h = (box[3].toInt() - t).coerceIn(1, f.height - t)
        val px = IntArray(w * h)
        f.getPixels(px, 0, w, l, t, w, h)
        return BlockStyle.sample(px, w, h)
    }

    override fun removeBlock(region: Int, key: String) {
        styles.remove("$region:$key")
        layer?.remove("$region:$key")
    }

    private fun onEvent(e: EngineEvent) {
        val s = session ?: return
        when (e) {
            is EngineEvent.OcrDone -> {
                if (s.owns(e.jobId)) log("ocr ${e.jobId}: " + e.paragraphs.joinToString(" | ") { r ->
                    r.joinToString(" / ") { "${it.kind} \"${it.text}\" @${it.left.toInt()},${it.top.toInt()}-${it.right.toInt()},${it.bottom.toInt()} h${it.lineHeight.toInt()}" }
                })
                frames.remove(e.jobId)?.let { lastOcrFrame = it }
                s.onOcrDone(e.jobId, e.paragraphs)
            }
            is EngineEvent.Partial -> {
                if (s.owns(e.jobId)) log("partial ${e.jobId}: " + e.segments.flatten().joinToString(" | ") { "\"${it.source}\" → \"${it.translation}\"" })
                s.onPartial(e.jobId, e.segments)
            }
            is EngineEvent.Done -> s.onJobEnded(e.jobId)
            is EngineEvent.JobFailed -> {
                frames.remove(e.jobId)
                if (s.owns(e.jobId)) log("job ${e.jobId} failed: ${e.why}")
                s.onJobFailed(e.jobId, superseded = e.why == SUPERSEDED)
            }
            is EngineEvent.SegmentReady -> Unit
        }
    }
}
