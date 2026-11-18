package dev.screentrans.ui

import android.content.Context
import dev.screentrans.core.RelRect

/** Remembered translation region (as fractions of the screen) and bubble position. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("screentrans", Context.MODE_PRIVATE)

    /** Translation regions; the old single "region" key is still read. */
    var regions: List<RelRect>
        get() = RelRect.parseList(sp.getString("regions", null) ?: sp.getString("region", null))
        set(value) = sp.edit().putString("regions", RelRect.serializeList(value)).remove("region").apply()

    var bubbleX: Int
        get() = sp.getInt("bubble_x", 0)
        set(v) = sp.edit().putInt("bubble_x", v).apply()

    var bubbleY: Int
        get() = sp.getInt("bubble_y", 400)
        set(v) = sp.edit().putInt("bubble_y", v).apply()
}
