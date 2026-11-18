package dev.screentrans.core.live

import kotlin.math.abs
import kotlin.math.roundToInt

/** Small gray thumbnails for change detection (same definition as windows/app/live/thumb.py). */
object Thumb {
    /** Gray (0.299R + 0.587G + 0.114B), box-averaged down to [targetW] px wide (aspect kept, never upscaled). */
    fun fromArgb(pixels: IntArray, w: Int, h: Int, targetW: Int = 64): FloatArray {
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

    /** Mean |Δ| per thumbnail pixel (0–255); different sizes → [Float.MAX_VALUE]. */
    fun diff(a: FloatArray, b: FloatArray): Float {
        if (a.size != b.size || a.isEmpty()) return Float.MAX_VALUE
        var total = 0.0
        for (i in a.indices) total += abs(a[i] - b[i])
        return (total / a.size).toFloat()
    }
}
