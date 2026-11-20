package dev.screentrans.core.live

import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Live "giống game" colours — port of windows/app/live/style.py; rules in shared/fixtures/live_style/README.md.
 */
data class BlockStyle(val textR: Int, val textG: Int, val textB: Int, val bgR: Int, val bgG: Int, val bgB: Int) {
    val textArgb: Int get() = (0xFF shl 24) or (textR shl 16) or (textG shl 8) or textB
    val bgArgb: Int get() = (0xFF shl 24) or (bgR shl 16) or (bgG shl 8) or bgB

    companion object {
        private const val BORDER = 2
        private const val BORDER_STD_MAX = 24.0
        private const val TEXT_SHARE = 0.15
        private const val MIN_CONTRAST = 3.0
        private const val FONT_PER_LINE = 0.8f

        const val STYLE_CELLS = 6

        /**
         * Which remembered "match" style a block uses (rules: shared/fixtures/live_style_cells): [left] / [top] of the
         * block inside its region of [w] x [h] px. Sampling every new block made the colours change all the time.
         */
        fun styleCell(left: Float, top: Float, w: Int, h: Int, kind: String): String {
            val col = (left * STYLE_CELLS / maxOf(1, w)).toInt().coerceIn(0, STYLE_CELLS - 1)
            val row = (top * STYLE_CELLS / maxOf(1, h)).toInt().coerceIn(0, STYLE_CELLS - 1)
            return "$kind:$col:$row"
        }

        /** Font size (px) for a source line of [lineHeight] px; null when unknown. */
        fun fontPxFor(lineHeight: Float): Float? = if (lineHeight > 0) lineHeight * FONT_PER_LINE else null

        private fun ch(c: Double): Double { val v = c / 255; return if (v <= 0.03928) v / 12.92 else ((v + 0.055) / 1.055).pow(2.4) }
        private fun lum(r: Double, g: Double, b: Double) = 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

        fun contrast(a: DoubleArray, b: DoubleArray): Double {
            val la = lum(a[0], a[1], a[2])
            val lb = lum(b[0], b[1], b[2])
            return (maxOf(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
        }

        private fun median(v: DoubleArray): Double {
            val s = v.sorted()
            val n = s.size
            return if (n % 2 == 1) s[n / 2] else (s[n / 2 - 1] + s[n / 2]) / 2
        }

        private fun rgb(c: Int) = doubleArrayOf(((c shr 16) and 0xFF).toDouble(), ((c shr 8) and 0xFF).toDouble(), (c and 0xFF).toDouble())

        /** [argb]: w x h pixels of one text block (its OCR box). Null → use the readable style. */
        fun sample(argb: IntArray, w: Int, h: Int): BlockStyle? {
            if (w < 2 * BORDER + 2 || h < 2 * BORDER + 2 || argb.size < w * h) return null
            val ring = ArrayList<DoubleArray>()
            val inner = ArrayList<DoubleArray>()
            for (y in 0 until h) for (x in 0 until w) {
                val px = rgb(argb[y * w + x])
                if (y < BORDER || y >= h - BORDER || x < BORDER || x >= w - BORDER) ring.add(px) else inner.add(px)
            }
            val luma = ring.map { 0.299 * it[0] + 0.587 * it[1] + 0.114 * it[2] }
            val mean = luma.average()
            val std = sqrt(luma.sumOf { (it - mean) * (it - mean) } / luma.size)
            if (std > BORDER_STD_MAX) return null
            val bg = DoubleArray(3) { c -> median(DoubleArray(ring.size) { ring[it][c] }) }
            val k = maxOf(1, (inner.size * TEXT_SHARE).toInt())
            val far = inner.sortedBy { p -> (0..2).sumOf { (p[it] - bg[it]) * (p[it] - bg[it]) } }.takeLast(k)
            val text = DoubleArray(3) { c -> median(DoubleArray(far.size) { far[it][c] }) }
            if (contrast(text, bg) < MIN_CONTRAST) return null
            val t = text.map { it.roundToInt() }
            val b = bg.map { it.roundToInt() }
            return BlockStyle(t[0], t[1], t[2], b[0], b[1], b[2])
        }
    }
}
