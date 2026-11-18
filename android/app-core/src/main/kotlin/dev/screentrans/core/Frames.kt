package dev.screentrans.core

/** Pure helpers on captured frames (ARGB pixels as Android's Bitmap.getPixels returns them). */
object Frames {
    /**
     * A game with FLAG_SECURE captures as a black frame. True when at least [threshold] of the
     * sampled pixels have luminance below 8 (a dark scene still has pixels above that).
     */
    fun isMostlyBlack(pixels: IntArray, threshold: Float = 0.98f, maxSamples: Int = 20_000): Boolean {
        if (pixels.isEmpty()) return true
        val step = maxOf(1, pixels.size / maxSamples)
        var dark = 0
        var total = 0
        var i = 0
        while (i < pixels.size) {
            val p = pixels[i]
            val r = (p shr 16) and 0xFF
            val g = (p shr 8) and 0xFF
            val b = p and 0xFF
            if ((r * 299 + g * 587 + b * 114) / 1000 < 8) dark++
            total++
            i += step
        }
        return dark >= threshold * total
    }

    /**
     * Report "game blocks capture" only when the frame looks black AND OCR found nothing: a dark
     * cutscene with thin light text also looks black on a thumbnail.
     */
    fun reportBlocked(mostlyBlack: Boolean, textFound: Boolean): Boolean = mostlyBlack && !textFound

    /** Clamp (l, t, r, b) to a width x height image; the result may be empty (r <= l or b <= t). */
    fun clampRect(width: Int, height: Int, l: Int, t: Int, r: Int, b: Int): IntArray =
        intArrayOf(l.coerceIn(0, width), t.coerceIn(0, height), r.coerceIn(0, width), b.coerceIn(0, height))
}
