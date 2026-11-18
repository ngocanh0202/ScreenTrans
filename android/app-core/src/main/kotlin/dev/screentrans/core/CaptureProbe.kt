package dev.screentrans.core

import kotlin.math.abs

/**
 * "Kiểm tra chụp màn hình": we draw a solid probe square, capture, and look at the pixels under it.
 * Tells whether our overlays end up in the MediaProjection frames (full-screen capture) or not
 * (single-app capture, Android 14+), which decides if Live must hide its overlays while capturing.
 */
object CaptureProbe {
    enum class Verdict { OVERLAY_CAPTURED, OVERLAY_HIDDEN, BLACK }

    private const val TOLERANCE = 40

    private fun close(a: Int, b: Int): Boolean =
        abs(((a shr 16) and 0xFF) - ((b shr 16) and 0xFF)) <= TOLERANCE &&
            abs(((a shr 8) and 0xFF) - ((b shr 8) and 0xFF)) <= TOLERANCE &&
            abs((a and 0xFF) - (b and 0xFF)) <= TOLERANCE

    /** [pixels]: ARGB pixels of the frame inside the probe square. */
    fun verdict(pixels: IntArray, probeColor: Int): Verdict {
        if (pixels.isEmpty()) return Verdict.BLACK
        val probe = pixels.count { close(it, probeColor) }
        if (probe * 3 >= pixels.size) return Verdict.OVERLAY_CAPTURED  // >= 1/3 of the square shows our color
        if (Frames.isMostlyBlack(pixels)) return Verdict.BLACK
        return Verdict.OVERLAY_HIDDEN
    }
}
