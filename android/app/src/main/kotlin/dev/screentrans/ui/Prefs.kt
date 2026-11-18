package dev.screentrans.ui

import android.content.Context
import dev.screentrans.core.RelRect

/** Remembered translation region (as fractions of the screen) and bubble position. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("screentrans", Context.MODE_PRIVATE)

    var region: RelRect?
        get() = RelRect.parse(sp.getString("region", null))
        set(value) = sp.edit().putString("region", value?.serialize()).apply()

    var bubbleX: Int
        get() = sp.getInt("bubble_x", 0)
        set(v) = sp.edit().putInt("bubble_x", v).apply()

    var bubbleY: Int
        get() = sp.getInt("bubble_y", 400)
        set(v) = sp.edit().putInt("bubble_y", v).apply()
}
