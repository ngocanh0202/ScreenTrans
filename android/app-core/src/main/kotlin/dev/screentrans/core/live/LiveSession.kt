package dev.screentrans.core.live

import screentrans.text.Paragraph
import screentrans.text.Segment

/** What a platform does for Live: capture + OCR, translate, draw. Ids identify engine jobs. */
interface LiveHost {
    /** Capture the watched regions (async is fine) and submit an OCR job; return its id. */
    fun requestOcr(): Int
    /** Submit a sentence-by-sentence translation of [paragraphs] (per region); return its id. */
    fun requestTranslate(paragraphs: List<List<Paragraph>>): Int
    /** Dialogue mode: translations per region, shown next to (never over) each region. */
    fun showDialogue(segments: List<List<Segment>>)
    /** Large-area mode: draw / remove the translation of one tracked text block. */
    fun setBlock(key: String, segment: Segment)
    fun removeBlock(key: String)
}

/**
 * Port of windows/app/live/controller.py without capture: frame diffs in, jobs out, results to the
 * overlays. Rules: [LiveMachine] (shared/fixtures/live), [BlockTracker] (shared/fixtures/live_blocks).
 * Main thread only.
 */
class LiveSession(
    params: LiveParams,
    val area: Boolean,
    areaMinIntervalMs: Int = 1000,
    areaMaxBlocks: Int = 30,
    private val host: LiveHost,
) {
    val machine = LiveMachine(params)
    private val tracker = BlockTracker(areaMaxBlocks)
    private val limiter = RateLimiter(areaMinIntervalMs)
    var running = true
        private set
    var ocrJob = -1
        private set
    var translateJob = -1
        private set
    private var pendingOcr = true  // translate what is already on screen
    private var pendingKeys: List<String> = emptyList()

    fun nextDelayMs(): Int = machine.nextDelayMs()

    fun stop() {
        running = false
        ocrJob = -1
        translateJob = -1
    }

    /** Our own overlay changed the screen (large-area mode on Android): the next frame is a new reference. */
    fun overlayChanged() = machine.onOverlayChanged()

    fun onFrame(nowMs: Int, diff: Float) {
        if (!running) return
        if (machine.onFrame(nowMs, diff) == LiveAction.OCR) pendingOcr = true
        if (pendingOcr && (!area || limiter.allow(nowMs))) {
            pendingOcr = false
            ocrJob = host.requestOcr()
        }
    }

    fun onOcrDone(jobId: Int, perRegion: List<List<Paragraph>>, nowMs: Int) {
        if (!running || jobId != ocrJob) return
        ocrJob = -1
        if (area) {
            val d = tracker.update(perRegion.flatten())
            d.removed.forEach { host.removeBlock(it.key) }
            if (d.removed.isNotEmpty()) machine.onOverlayChanged()
            if (d.added.isNotEmpty()) {
                pendingKeys = d.added.map { it.key }
                translateJob = host.requestTranslate(listOf(d.added.map { it.paragraph }))
            }
            return
        }
        val text = perRegion.flatten().joinToString(" ") { it.text }
        if (machine.onText(nowMs, text) == "translate") translateJob = host.requestTranslate(perRegion)
    }

    fun onPartial(jobId: Int, perRegion: List<List<Segment>>) {
        if (!running || jobId != translateJob) return
        if (area) {
            pendingKeys.zip(perRegion.flatten()).forEach { (key, seg) -> host.setBlock(key, seg) }
            machine.onOverlayChanged()
            return
        }
        host.showDialogue(perRegion)
        machine.onOverlayChanged()  // our own card may show up in the next frame
    }

    /** Done: the job no longer counts as running. */
    fun onJobEnded(jobId: Int) {
        if (jobId == ocrJob) ocrJob = -1
        if (jobId == translateJob) translateJob = -1
    }

    /** Failed / superseded: nothing was shown, so the same text / blocks are translated next time. */
    fun onJobFailed(jobId: Int) {
        if (jobId == translateJob) {
            if (area) {
                tracker.forget(pendingKeys)
                pendingKeys = emptyList()
            } else {
                machine.forgetTranslation()
            }
        }
        onJobEnded(jobId)
    }

    /** Tests only. */
    fun debugSetOcrJob(id: Int) {
        ocrJob = id
    }
}
