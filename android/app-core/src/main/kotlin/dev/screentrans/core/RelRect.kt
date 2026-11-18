package dev.screentrans.core

import kotlin.math.roundToInt

/** A screen region as fractions (0-1) of the screen, so it survives rotation and resolution changes. */
data class RelRect(val l: Float, val t: Float, val r: Float, val b: Float) {
    fun toPx(w: Int, h: Int): IntArray =
        intArrayOf((l * w).roundToInt(), (t * h).roundToInt(), (r * w).roundToInt(), (b * h).roundToInt())

    fun isUsable(w: Int, h: Int): Boolean {
        val px = toPx(w, h)
        return px[2] - px[0] >= MIN_PX && px[3] - px[1] >= MIN_PX
    }

    fun serialize(): String = "$l,$t,$r,$b"

    companion object {
        const val MIN_PX = 8

        fun fromPx(x0: Int, y0: Int, x1: Int, y1: Int, w: Int, h: Int): RelRect {
            fun fx(v: Int) = (v.coerceIn(0, w).toFloat() / w)
            fun fy(v: Int) = (v.coerceIn(0, h).toFloat() / h)
            return RelRect(fx(minOf(x0, x1)), fy(minOf(y0, y1)), fx(maxOf(x0, x1)), fy(maxOf(y0, y1)))
        }

        fun parse(s: String?): RelRect? {
            val p = s?.split(",")?.mapNotNull { it.toFloatOrNull() } ?: return null
            return if (p.size == 4) RelRect(p[0], p[1], p[2], p[3]) else null
        }
    }
}
