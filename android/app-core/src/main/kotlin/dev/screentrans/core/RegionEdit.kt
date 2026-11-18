package dev.screentrans.core

/** Pure maths for the region editor: corner handles resize, the body moves, rects stay on screen. */
object RegionEdit {
    const val MIN_SIZE = 48

    enum class Part { TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT, BODY }

    data class Hit(val index: Int, val part: Part)

    /** Rects are (l, t, r, b) in px. Corners win over bodies; later (top-most) rects win. */
    fun hitTest(rects: List<IntArray>, x: Int, y: Int, handle: Int): Hit? {
        fun near(px: Int, py: Int) = kotlin.math.abs(x - px) <= handle && kotlin.math.abs(y - py) <= handle
        for (i in rects.indices.reversed()) {
            val (l, t, r, b) = rects[i].toList()
            when {
                near(l, t) -> return Hit(i, Part.TOP_LEFT)
                near(r, t) -> return Hit(i, Part.TOP_RIGHT)
                near(l, b) -> return Hit(i, Part.BOTTOM_LEFT)
                near(r, b) -> return Hit(i, Part.BOTTOM_RIGHT)
            }
        }
        for (i in rects.indices.reversed()) {
            val (l, t, r, b) = rects[i].toList()
            if (x in l..r && y in t..b) return Hit(i, Part.BODY)
        }
        return null
    }

    /** Rect after dragging `part` by (dx, dy) on a w x h screen. */
    fun drag(rect: IntArray, part: Part, dx: Int, dy: Int, w: Int, h: Int): IntArray {
        var (l, t, r, b) = rect.toList()
        when (part) {
            Part.BODY -> {
                val rw = r - l
                val rh = b - t
                l = (l + dx).coerceIn(0, maxOf(0, w - rw)); t = (t + dy).coerceIn(0, maxOf(0, h - rh))
                r = l + rw; b = t + rh
            }
            Part.TOP_LEFT -> { l = (l + dx).coerceIn(0, r - MIN_SIZE); t = (t + dy).coerceIn(0, b - MIN_SIZE) }
            Part.TOP_RIGHT -> { r = (r + dx).coerceIn(l + MIN_SIZE, w); t = (t + dy).coerceIn(0, b - MIN_SIZE) }
            Part.BOTTOM_LEFT -> { l = (l + dx).coerceIn(0, r - MIN_SIZE); b = (b + dy).coerceIn(t + MIN_SIZE, h) }
            Part.BOTTOM_RIGHT -> { r = (r + dx).coerceIn(l + MIN_SIZE, w); b = (b + dy).coerceIn(t + MIN_SIZE, h) }
        }
        return intArrayOf(l, t, r, b)
    }
}
