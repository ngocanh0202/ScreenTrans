package screentrans.text

import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * Tilted text — port of windows/app/ocr/deskew.py. Lines are expressed in a frame rotated by -angle around
 * the image origin (0, 0); overlays rotate back by +angle. Degrees, clockwise positive (as ML Kit).
 */
object Deskew {
    const val STRAIGHT_DEG = 2f

    /** Screen point -> tilted (straightened) frame. */
    fun rotate(x: Float, y: Float, angle: Float): Pair<Float, Float> {
        val a = Math.toRadians(angle.toDouble())
        return (x * cos(a) + y * sin(a)).toFloat() to (-x * sin(a) + y * cos(a)).toFloat()
    }

    /** Tilted frame -> screen point. */
    fun unrotate(x: Float, y: Float, angle: Float): Pair<Float, Float> {
        val a = Math.toRadians(angle.toDouble())
        return (x * cos(a) - y * sin(a)).toFloat() to (x * sin(a) + y * cos(a)).toFloat()
    }

    /** Four corners (clockwise from top-left, screen px) of a tilted line -> [left, top, width, height] in its frame. */
    fun fromCorners(points: List<Pair<Float, Float>>, angle: Float): FloatArray {
        val cx = points.sumOf { it.first.toDouble() }.toFloat() / 4
        val cy = points.sumOf { it.second.toDouble() }.toFloat() / 4
        val width = hypot(points[1].first - points[0].first, points[1].second - points[0].second)
        val height = hypot(points[2].first - points[1].first, points[2].second - points[1].second)
        val (dcx, dcy) = rotate(cx, cy, angle)
        return floatArrayOf(dcx - width / 2, dcy - height / 2, width, height)
    }

    /** Angle (degrees, clockwise) of a line from its corners (top-left -> top-right), sign-proof. */
    fun angleOf(points: List<Pair<Float, Float>>): Float =
        Math.toDegrees(kotlin.math.atan2((points[1].second - points[0].second).toDouble(), (points[1].first - points[0].first).toDouble())).toFloat()

    /** Screen bounding box [l, t, r, b] of a tilted-frame box [l, t, r, b] (e.g. to crop the image). */
    fun bounds(box: FloatArray, angle: Float): FloatArray {
        if (angle == 0f) return box.copyOf()
        val pts = listOf(box[0] to box[1], box[2] to box[1], box[2] to box[3], box[0] to box[3]).map { (x, y) -> unrotate(x, y, angle) }
        return floatArrayOf(pts.minOf { it.first }, pts.minOf { it.second }, pts.maxOf { it.first }, pts.maxOf { it.second })
    }
}
