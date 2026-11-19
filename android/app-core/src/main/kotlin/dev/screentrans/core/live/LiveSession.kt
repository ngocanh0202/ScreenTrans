package dev.screentrans.core.live

import screentrans.text.Kind
import screentrans.text.Paragraph
import screentrans.text.Segment

/** What a platform does for Live: capture + OCR, translate, draw. Ids identify engine jobs. */
interface LiveHost {
    /** Capture the watched regions (async is fine) and submit an OCR job; return its id. */
    fun requestOcr(final: Boolean): Int
    /** Submit a sentence-by-sentence translation of [paragraphs] (per region); return its id. */
    fun requestTranslate(paragraphs: List<List<Paragraph>>): Int
    /** Draw (or redraw in place) one text block's translation over it; [box] = l, t, r, b in frame pixels. */
    fun setBlock(region: Int, key: String, text: String, box: FloatArray, kind: Kind, lineHeight: Float, angle: Float)
    fun removeBlock(region: Int, key: String)
}

/**
 * Port of windows/app/live/controller.py (4b) without capture: frame diffs in, jobs out, blocks drawn
 * over the source text, each sentence as soon as it is finished. Rules: [LiveMachine]
 * (shared/fixtures/live), [BlockTracker] (live_blocks), [SentenceGate] (live_sentences). Main thread only.
 */
/** A block whose text did not change for this long has stopped typing / fading in. */
const val KEPT_FINAL_MS = 1500
const val KNOWN_MAX = 500  // translations remembered by source sentence (shown again at once, no engine job)

class LiveSession(
    params: LiveParams,
    val scope: String,
    private val regionCount: Int,
    areaMinIntervalMs: Int = 1000,
    areaMaxBlocks: Int = 30,
    private val host: LiveHost,
) {
    private class BlockState {
        var kind = Kind.TEXT
        var box = FloatArray(4)
        var sentences: List<String> = emptyList()
        var done = 0
        val shown = HashMap<Int, Pair<String, String>>()  // index -> (source, translation)
        var drawn = ""
        var drawnBox = FloatArray(0)
        var lineHeight = 0f
        var stableSince = 0  // when its text last changed
        var angle = 0f       // tilted text
    }

    private data class Item(val region: Int, val key: String, val index: Int, val source: String)

    val machine = LiveMachine(params)
    private val trackers = List(regionCount) { BlockTracker(areaMaxBlocks) }
    private val limiter = RateLimiter(areaMinIntervalMs)
    private val blocks = HashMap<Pair<Int, String>, BlockState>()
    private val ocrFinal = HashMap<Int, Boolean>()
    private val requests = HashMap<Int, List<Item>>()
    private val inflight = HashSet<Item>()
    private val fixed = HashMap<String, String>()  // the user's corrections: a late machine translation never wins
    private val known = LinkedHashMap<String, String>()  // sentence -> translation shown in this run (oldest first)

    private fun remember(source: String, translation: String) {
        known.remove(source)
        known[source] = translation
        while (known.size > KNOWN_MAX) known.remove(known.keys.first())
    }
    private var pending: Boolean? = true  // translate what is already on screen; true = final OCR
    private var lastNow = 0
    var running = true
        private set
    var ocrJob = -1
        private set

    /** Our overlays end up in the captured frames (full-screen capture): ignore our own redraws. */
    var overlaysInCapture = false

    /** Translations shown last (for "edit the last translation"). */
    var lastSegments: List<Segment> = emptyList()
        private set

    fun nextDelayMs(): Int = machine.nextDelayMs()

    fun owns(jobId: Int): Boolean = jobId == ocrJob || jobId in ocrFinal || jobId in requests

    fun stop() {
        running = false
        ocrJob = -1
        ocrFinal.clear(); requests.clear(); inflight.clear(); blocks.clear()
        pending = null
    }

    /** Our own overlay changed the screen: the next frame is only a new reference. */
    fun overlayChanged() = machine.onOverlayChanged()

    fun onFrame(nowMs: Int, diff: Float) {
        lastNow = nowMs
        if (!running) return
        when (machine.onFrame(nowMs, diff)) {
            LiveAction.OCR -> {
                pending = machine.final || pending == true
                if (!machine.final) machine.rearm(nowMs)  // max_wait: a final read must still follow when still
            }
            LiveAction.PARTIAL -> if (ocrJob == -1 && pending == null) pending = false
            LiveAction.WAIT -> Unit
        }
        val p = pending ?: return
        if (scope == "screen" && !limiter.allow(nowMs)) return
        pending = null
        val id = host.requestOcr(p)
        ocrFinal[id] = p
        ocrJob = id
    }

    fun onOcrDone(jobId: Int, perRegion: List<List<Paragraph>?>, nowMs: Int = lastNow) {
        val final = ocrFinal.remove(jobId) ?: return
        if (!running) return
        if (jobId == ocrJob) ocrJob = -1
        val request = mutableListOf<Item>()
        perRegion.take(regionCount).forEachIndexed { i, paragraphs ->
            if (paragraphs == null) return@forEachIndexed
            val d = trackers[i].update(paragraphs.filter(LiveFilter::worthTranslating))  // no OCR noise / labels
            val carry = HashMap<String, String>()  // translations of blocks that only got a new key
            for (b in d.removed) {
                blocks.remove(i to b.key)?.shown?.values?.forEach { (src, tr) -> carry[src] = tr }
                host.removeBlock(i, b.key)
                changedOverlay()
            }
            // same text for KEPT_FINAL_MS: stopped typing, even while the screen animates (and not just faded in)
            val kept = d.kept.filter { b -> blocks[i to b.key]?.let { nowMs - it.stableSince >= KEPT_FINAL_MS } == true }
                .map { it.key }.toSet()
            for (b in d.added + d.grown + d.kept) request += updateBlock(i, b.key, b.paragraph, final || b.key in kept, carry, nowMs)
        }
        request(request)
    }

    private fun request(request: List<Item>) {
        if (request.isEmpty()) return
        val groups = List(regionCount) { mutableListOf<Paragraph>() }
        for (it in request) {
            val b = blocks.getValue(it.region to it.key).box
            groups[it.region].add(Paragraph(Kind.TEXT, it.source, listOf(it.source), b[0], b[1], b[2], b[3]))
        }
        val id = host.requestTranslate(groups)
        requests[id] = request
        inflight += request
    }

    private fun updateBlock(i: Int, key: String, p: Paragraph, final: Boolean, carry: Map<String, String>, nowMs: Int): List<Item> {
        val st = blocks.getOrPut(i to key) { BlockState() }
        st.kind = p.kind
        if (p.lineHeight > 0) st.lineHeight = p.lineHeight
        st.angle = p.angle
        st.box = floatArrayOf(p.left, p.top, p.right, p.bottom)
        if (p.kind == Kind.NAME) {
            st.sentences = listOf(p.text)
            st.done = 1
            draw(i, key)
            return emptyList()
        }
        if (p.sentences != st.sentences || st.sentences.isEmpty()) st.stableSince = nowMs
        st.done = SentenceGate.done(p.sentences, st.sentences.ifEmpty { null }, final)
        st.sentences = p.sentences
        st.shown.keys.removeAll { k -> k >= st.sentences.size || st.sentences[k] != st.shown.getValue(k).first }
        for (k in 0 until st.done) {
            val tr = carry[st.sentences[k]] ?: known[st.sentences[k]]
            if (k !in st.shown && tr != null) st.shown[k] = st.sentences[k] to tr
        }
        draw(i, key)
        return (0 until st.done).map { Item(i, key, it, st.sentences[it]) }
            .filter { it.index !in st.shown && it !in inflight }
    }

    private fun draw(i: Int, key: String) {
        val st = blocks[i to key] ?: return
        val text = if (st.kind == Kind.NAME) st.sentences.firstOrNull().orEmpty()
        else (0 until st.done).mapNotNull { st.shown[it]?.second }.joinToString(" ")
        if (text == st.drawn && st.box.contentEquals(st.drawnBox)) return
        st.drawn = text
        st.drawnBox = st.box.copyOf()
        if (text.isEmpty()) host.removeBlock(i, key) else host.setBlock(i, key, text, st.box, st.kind, st.lineHeight, st.angle)
        changedOverlay()
    }

    private fun changedOverlay() {
        if (overlaysInCapture) machine.onOverlayChanged()
    }

    fun onPartial(jobId: Int, perRegion: List<List<Segment>>) {
        val request = requests[jobId] ?: return
        if (!running) return
        val flat = perRegion.flatten()
        val touched = LinkedHashSet<Pair<Int, String>>()
        request.zip(flat).forEach { (item, seg) ->
            val st = blocks[item.region to item.key] ?: return@forEach
            val tr = seg.translation
            if (tr.isNullOrEmpty() || tr == "…" || item.index >= st.sentences.size || st.sentences[item.index] != item.source) return@forEach
            st.shown[item.index] = item.source to (fixed[item.source] ?: tr)
            remember(item.source, st.shown.getValue(item.index).second)
            touched += item.region to item.key
        }
        touched.forEach { (i, key) -> draw(i, key) }
        lastSegments = flat
    }

    /** Every translated sentence on screen now (for "edit the last translation"). */
    fun shownSegments(): List<Segment> = blocks.values.filter { it.kind == Kind.TEXT }.flatMap { st ->
        (0 until st.done).mapNotNull { k ->
            st.shown[k]?.let { (src, tr) -> Segment(Kind.TEXT, src, tr, st.box[0], st.box[1], st.box[2], st.box[3]) }
        }
    }

    /** The user fixed a sentence: redraw every block showing it. */
    fun applyCorrection(source: String, corrected: String) {
        fixed[source] = corrected
        if (source in known) remember(source, corrected)
        for ((key, st) in blocks) {
            val hit = st.shown.filterValues { it.first == source }.keys
            if (hit.isEmpty()) continue
            hit.forEach { st.shown[it] = source to corrected }
            draw(key.first, key.second)
        }
    }

    /** Done: the job no longer counts as running. */
    fun onJobEnded(jobId: Int) {
        requests.remove(jobId)?.let { inflight -= it.toSet() }
    }

    /** Finished sentences that are neither shown nor being translated. */
    private fun missing(): List<Item> = blocks.entries.filter { it.value.kind == Kind.TEXT }.flatMap { (k, st) ->
        (0 until st.done).map { Item(k.first, k.second, it, st.sentences[it]) }.filter { it.index !in st.shown && it !in inflight }
    }

    /**
     * Failed / superseded. A superseded translation is asked again at once (the screen may stay still now that
     * the line is complete); after a real error the sentences wait for the next OCR.
     */
    fun onJobFailed(jobId: Int, superseded: Boolean = false) {
        if (ocrFinal.remove(jobId) == true && running) pending = true  // the final read was lost: read again
        if (jobId == ocrJob) ocrJob = -1
        val wasTranslation = jobId in requests
        onJobEnded(jobId)
        if (wasTranslation && superseded && running) request(missing())
    }

    /** Tests only: pretend an OCR job [id] was requested. */
    fun debugExpectOcr(id: Int, final: Boolean) {
        ocrFinal[id] = final
        ocrJob = id
    }
}
