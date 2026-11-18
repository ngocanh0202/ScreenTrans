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
