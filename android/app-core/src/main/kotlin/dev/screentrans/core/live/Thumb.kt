package dev.screentrans.core.live

import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * Small gray thumbnails for change detection (same definition as windows/app/live/thumb.py).
 * A change = how many cells changed clearly: a mean over the thumbnail hid a new dialogue line on a full
 * screen (< 1), so Live only ever read the first line.
 */
object Thumb {
    const val WIDTH = 160
    const val CELL_DELTA = 16f  // a cell changed when its gray level moved by more than this (0-255)

    /** Gray (0.299R + 0.587G + 0.114B), box-averaged down to [targetW] px wide (aspect kept, never upscaled). */
    fun fromArgb(pixels: IntArray, w: Int, h: Int, targetW: Int = WIDTH): FloatArray {
        require(w > 0 && h > 0 && pixels.size >= w * h)
        val tw = minOf(targetW, w)
        val th = maxOf(1, (h.toFloat() * tw / w).roundToInt())
        val sum = FloatArray(tw * th)
        val count = IntArray(tw * th)
        for (y in 0 until h) {
            val ty = minOf(th - 1, y * th / h)
            val row = y * w
            for (x in 0 until w) {
                val c = pixels[row + x]
                val gray = 0.299f * ((c shr 16) and 0xFF) + 0.587f * ((c shr 8) and 0xFF) + 0.114f * (c and 0xFF)
                val i = ty * tw + minOf(tw - 1, x * tw / w)
                sum[i] += gray
                count[i]++
            }
        }
        for (i in sum.indices) if (count[i] > 0) sum[i] /= count[i]
        return sum
    }

    /** Number of cells whose gray level changed by more than [CELL_DELTA], only where [mask] is true; different sizes → [Float.MAX_VALUE]. */
    fun diff(a: FloatArray, b: FloatArray, mask: BooleanArray? = null): Float {
        if (a.size != b.size || a.isEmpty()) return Float.MAX_VALUE
        val m = mask?.takeIf { it.size == a.size }
        var count = 0
        for (i in a.indices) {
            if (m != null && !m[i]) continue
            if (abs(a[i] - b[i]) > CELL_DELTA) count++
        }
        return count.toFloat()  // everything ignored: 0, "no change"
    }
}
