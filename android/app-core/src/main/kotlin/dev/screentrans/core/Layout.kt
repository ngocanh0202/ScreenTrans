package dev.screentrans.core

import kotlin.math.ceil

/** Pure placement maths for the Android overlays (same rules as windows/app/gui/overlay.py). */
object Layout {
    const val MIN_TEXT_PX = 9f * 2.75f  // 9 sp at ~440 dpi (POCO X8 Pro), the smallest readable size
    private const val CHAR_WIDTH = 0.55f   // average glyph width / text size for Latin+Vietnamese
    private const val LINE_HEIGHT = 1.25f
    private const val GROW = 1.5f          // a block may grow to 150% of the source text height

    /**
     * Top-left (x, y) for a w x h overlay next to `region` = (l, t, r, b), r/b exclusive:
     * below the region, above when the bottom overflows, clamped inside the screen.
     */
    fun placeOverlay(region: IntArray, w: Int, h: Int, screenW: Int, screenH: Int, gap: Int = 12): IntArray {
        val x = region[0].coerceAtMost(screenW - w).coerceAtLeast(0)
        val below = region[3] + gap
        if (below + h <= screenH) return intArrayOf(x, below)
        val above = region[1] - gap - h
        if (above >= 0) return intArrayOf(x, above)
        return intArrayOf(x, (screenH - h).coerceAtLeast(0))
    }

    /**
     * Live card position outside every watched region (spec §5.6: above by default, else below), so
     * the card never enters a Live capture. Null when neither fits; the caller then hides it while capturing.
     */
    fun placeOutside(
        region: IntArray, w: Int, h: Int, screenW: Int, screenH: Int, avoid: List<IntArray>, gap: Int = 12,
    ): IntArray? {
        val x = region[0].coerceAtMost(screenW - w).coerceAtLeast(0)
        fun clear(y: Int) = avoid.none { a -> x < a[2] && x + w > a[0] && y < a[3] && y + h > a[1] }
        val above = region[1] - gap - h
        if (above >= 0 && clear(above)) return intArrayOf(x, above)
        val below = region[3] + gap
        if (below + h <= screenH && clear(below)) return intArrayOf(x, below)
        return null
    }

    /** Live translations start this much (x text size) above the source box: they looked a little low. */
    const val LIFT = 0.2f

    /** Top of a Live translation box (its bottom stays, so the source line is still covered). */
    fun liftedTop(top: Float, textPx: Float, tilted: Boolean): Float {
        val lift = textPx * LIFT
        return if (tilted) top - lift else top - minOf(lift, maxOf(0f, top))
    }

    /** Translation box fit: font size and drawn height (px). The whole text is always shown (never cut). */
    data class Fit(val px: Float, val height: Int)

    /**
     * Live block fit. [grow]: keep [basePx], the box is as tall as the text needs (it may run past the source).
     * Otherwise the font shrinks down to [MIN_TEXT_PX] to fit 1.5x the source height; still too long → it grows.
     */
    fun fitBlock(textLen: Int, blockW: Int, blockH: Int, basePx: Float, grow: Boolean): Fit {
        fun needed(size: Float): Int {
            val perLine = maxOf(1f, blockW / (CHAR_WIDTH * size))
            return (ceil(textLen / perLine) * LINE_HEIGHT * size).toInt()
        }
        var size = basePx
        if (!grow) {
            while (needed(size) > blockH * GROW && size > MIN_TEXT_PX) size = maxOf(MIN_TEXT_PX, size - 1f)
        }
        return Fit(size, maxOf(needed(size), blockH))
    }

    private const val WIDEN_SHARE = 0.25f  // a box may grow this much of its width...
    private const val WIDEN_EMS = 4f       // ...or this many text sizes (a short source: "Hello" -> "Xin chào")

    /**
     * Live box width (port of windows/app/live/layout.py, rules in shared/fixtures/live_layout): the source [width],
     * or the smallest wider one up to the cap that needs as few [lines] as the cap. Vietnamese runs longer than
     * English: a short source dropped its last word to a new line.
     */
    fun widen(width: Int, lines: (Int) -> Int, room: Int, px: Float): Int {
        val cap = minOf(room, width + maxOf((WIDEN_SHARE * width).toInt(), (WIDEN_EMS * px).toInt()))
        if (cap <= width) return width
        val target = lines(cap)
        if (lines(width) <= target) return width
        var lo = width
        var hi = cap
        while (hi - lo > 1) {
            val mid = (lo + hi) / 2
            if (lines(mid) <= target) hi = mid else lo = mid
        }
        return hi
    }

    /**
     * Boxes (l, t, r, b) moved down until none covers another, upper ones first; input order kept. A translation
     * taller than its source used to cover the next block's translation.
     */
    fun separate(rects: List<FloatArray>, gap: Float = 2f): List<FloatArray> {
        val order = rects.indices.sortedWith(compareBy({ rects[it][1] }, { rects[it][0] }))
        val placed = mutableListOf<FloatArray>()
        val out = rects.map { it.copyOf() }.toMutableList()
        for (i in order) {
            val (l, t0, r, b0) = rects[i]
            var t = t0
            var b = b0
            var moved = true
            while (moved) {
                moved = false
                for (p in placed) {
                    if (l < p[2] && r > p[0] && t < p[3] && b > p[1]) {
                        val h = b - t
                        t = p[3] + gap
                        b = t + h
                        moved = true
                    }
                }
            }
            out[i] = floatArrayOf(l, t, r, b)
            placed.add(out[i])
        }
        return out
    }

    /** Top of a box of [height] px starting at [top]: moved up so it ends on screen, never above the top. */
    fun onScreenTop(top: Float, height: Int, screenH: Int): Float =
        maxOf(0f, minOf(top, (screenH - height).toFloat()))

    /**
     * Top-left of a [size] px square button at the real bottom-right corner of [box] (l, t, r, b in a frame
     * tilted by [angle] around (0, 0)), kept inside the screen.
     */
    fun cornerOnScreen(box: FloatArray, angle: Float, size: Int, screenW: Int, screenH: Int): Pair<Int, Int> {
        val (cx, cy) = screentrans.text.Deskew.unrotate(box[2], box[3], angle)
        return (cx - size).toInt().coerceIn(0, maxOf(0, screenW - size)) to (cy - size / 2).toInt().coerceIn(0, maxOf(0, screenH - size))
    }

    private val SCALES = listOf(0.8f, 1f, 1.25f, 1.5f)

    /** Translation text size steps (settings "Cỡ chữ"). */
    fun nextScale(s: Float): Float = SCALES.firstOrNull { it > s + 0.01f } ?: SCALES.last()
    fun prevScale(s: Float): Float = SCALES.lastOrNull { it < s - 0.01f } ?: SCALES.first()

    /** Keep a size x size bubble fully on a w x h screen (a position saved in portrait may be off-screen). */
    fun clampBubble(x: Int, y: Int, size: Int, w: Int, h: Int): IntArray =
        intArrayOf(x.coerceIn(0, maxOf(0, w - size)), y.coerceIn(0, maxOf(0, h - size)))

    /** Largest text size in [MIN_TEXT_PX, basePx] whose estimated wrapped height fits blockH * GROW. */
    fun fitTextPx(textLen: Int, blockW: Int, blockH: Int, basePx: Float): Float {
        if (basePx <= MIN_TEXT_PX) return basePx
        var size = basePx
        while (size > MIN_TEXT_PX) {
            val perLine = maxOf(1f, blockW / (CHAR_WIDTH * size))
            val lines = ceil(textLen / perLine)
            if (lines * LINE_HEIGHT * size <= blockH * GROW) return size
            size -= 1f
        }
        return MIN_TEXT_PX
    }
}
