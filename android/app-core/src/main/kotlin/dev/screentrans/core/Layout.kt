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
