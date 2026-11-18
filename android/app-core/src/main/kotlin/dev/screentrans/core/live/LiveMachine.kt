package dev.screentrans.core.live

import screentrans.text.Paragraph
import screentrans.text.normalizeText
import kotlin.math.hypot

/** Port of windows/app/live/machine.py — rules in shared/fixtures/live/README.md. */
data class LiveParams(
    val intervalMs: Int = 300,
    val activeIntervalMs: Int = 100,
    val settleMs: Int = 250,
    val maxWaitMs: Int = 2000,
    val changeThreshold: Float = 5f,
)

enum class LiveAction { WAIT, OCR }

class LiveMachine(private val p: LiveParams = LiveParams()) {
    var changing = false
        private set
    private var changedAt = 0
    private var lastChange = 0
    private var byMaxWait = false
    private var lastOcr = ""
    private var lastTranslated = ""
    private var suppressNext = false

    fun nextDelayMs(): Int = if (changing) p.activeIntervalMs else p.intervalMs

    /** Our own overlay was redrawn: the next frame is only a new reference. */
    fun onOverlayChanged() {
        suppressNext = true
    }

    fun onFrame(nowMs: Int, diff: Float): LiveAction {
        if (suppressNext) {
            suppressNext = false
            return LiveAction.WAIT
        }
        val changed = diff > p.changeThreshold
        if (!changing) {
            if (changed) {
                changing = true
                changedAt = nowMs
                lastChange = nowMs
            }
            return LiveAction.WAIT
        }
        if (changed) lastChange = nowMs
        if (nowMs - lastChange >= p.settleMs) {
            changing = false; byMaxWait = false
            return LiveAction.OCR
        }
        if (nowMs - changedAt >= p.maxWaitMs) {
            changing = false; byMaxWait = true
            return LiveAction.OCR
        }
        return LiveAction.WAIT
    }

    /** "translate", "skip" or "wait". */
    fun onText(nowMs: Int, text: String): String {
        val t = normalizeText(text)
        if (t.isEmpty()) {
            lastOcr = ""
            return "skip"
        }
        if (t == lastTranslated) {
            lastOcr = t
            return "skip"
        }
        if (byMaxWait && t != lastOcr) {  // may still be typing: translate once it settles or repeats
            lastOcr = t
            changing = true
            changedAt = nowMs
            return "wait"
        }
        lastOcr = t
        lastTranslated = t
        return "translate"
    }
}

/** Port of windows/app/live/blocks.py — rules in shared/fixtures/live_blocks/README.md. */
data class Block(val key: String, val text: String, val paragraph: Paragraph) {
    val cx: Float get() = (paragraph.left + paragraph.right) / 2
    val cy: Float get() = (paragraph.top + paragraph.bottom) / 2
}

data class BlockDiff(val added: List<Block>, val kept: List<Block>, val removed: List<Block>)

class BlockTracker(private val maxBlocks: Int = 30, private val nearPx: Float = 24f) {
    var shown: List<Block> = emptyList()
        private set
    private var nextId = 1

    fun update(paragraphs: List<Paragraph>): BlockDiff {
        val paras = paragraphs.sortedWith(compareBy({ it.top }, { it.left })).take(maxBlocks)
        val free = shown.toMutableList()
        val added = mutableListOf<Block>()
        val kept = mutableListOf<Block>()
        val now = mutableListOf<Block>()
        for (p in paras) {
            val text = normalizeText(p.text)
            val cx = (p.left + p.right) / 2
            val cy = (p.top + p.bottom) / 2
            val match = free.firstOrNull { it.text == text && hypot(it.cx - cx, it.cy - cy) <= nearPx }
            val block = if (match != null) {
                free.remove(match)
                Block(match.key, text, p).also { kept.add(it) }
            } else {
                Block("b${nextId++}", text, p).also { added.add(it) }
            }
            now.add(block)
        }
        shown = now
        return BlockDiff(added, kept, free)
    }
}

/** At most one OCR per minIntervalMs (large-area Live). */
class RateLimiter(private val minIntervalMs: Int = 1000) {
    private var last: Int? = null

    fun allow(nowMs: Int): Boolean {
        val l = last
        if (l != null && nowMs - l < minIntervalMs) return false
        last = nowMs
        return true
    }
}
