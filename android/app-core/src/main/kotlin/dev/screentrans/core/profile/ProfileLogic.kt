package dev.screentrans.core.profile

import dev.screentrans.core.RelRect
import kotlin.math.ceil
import kotlin.math.floor

/** Pure rules around game profiles on Android (JVM-tested; the app only does I/O). */
object ProfileLogic {
    /** Manual choice > the app in front > the default profile; our own app is never a game. */
    fun pickGame(foreground: String?, manual: String?, own: String): String =
        manual?.takeIf { it.isNotEmpty() }
            ?: foreground?.takeIf { it.isNotEmpty() && it != own }
            ?: Profile.DEFAULT_ID

    /** Phase 3-4a kept the regions and the Live mode in SharedPreferences: they become the default profile. */
    fun migratePrefs(regions: List<RelRect>, liveScope: String): Profile =
        withRegions(Profile(Profile.DEFAULT_ID, "Mặc định", scope = if (liveScope == "screen") "screen" else "region"), regions)

    // Float -> Double through the decimal text (0.7f stays 0.7, not 0.69999998), rounded to 6 decimals.
    private fun d(v: Float) = v.toString().toDouble()
    private fun round6(v: Double) = Math.round(v * 1e6) / 1e6
    private fun toXywh(r: RelRect) = listOf(round6(d(r.l)), round6(d(r.t)), round6(d(r.r) - d(r.l)), round6(d(r.b) - d(r.t)))

    private fun toRel(v: List<Double>) = RelRect(v[0].toFloat(), v[1].toFloat(), (v[0] + v[2]).toFloat(), (v[1] + v[3]).toFloat())

    fun regionsOf(p: Profile): List<RelRect> = p.regions.map(::toRel)
    fun ignoreOf(p: Profile): List<RelRect> = p.ignore.map(::toRel)
    fun withRegions(p: Profile, rects: List<RelRect>): Profile = p.copy(regions = rects.map(::toXywh))
    fun withIgnore(p: Profile, rects: List<RelRect>): Profile = p.copy(ignore = rects.map(::toXywh))

    /**
     * Row-major (th x tw) mask for a thumbnail of [regionPx] (l, t, r, b): true where pixels are compared,
     * false under any of [ignorePx] (same as windows/app/live/mask.py).
     */
    fun ignoreMask(regionPx: IntArray, ignorePx: List<IntArray>, tw: Int, th: Int): BooleanArray {
        val keep = BooleanArray(tw * th) { true }
        val rw = regionPx[2] - regionPx[0]
        val rh = regionPx[3] - regionPx[1]
        if (rw <= 0 || rh <= 0) return keep
        for (ig in ignorePx) {
            val x0 = floor((ig[0] - regionPx[0]).toDouble() * tw / rw).toInt().coerceIn(0, tw)
            val y0 = floor((ig[1] - regionPx[1]).toDouble() * th / rh).toInt().coerceIn(0, th)
            val x1 = ceil((ig[2] - regionPx[0]).toDouble() * tw / rw).toInt().coerceIn(0, tw)
            val y1 = ceil((ig[3] - regionPx[1]).toDouble() * th / rh).toInt().coerceIn(0, th)
            for (y in y0 until y1) for (x in x0 until x1) keep[y * tw + x] = false
        }
        return keep
    }
}
