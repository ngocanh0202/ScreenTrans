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

    /** Live scope: "screen" or "region" (default; the 4a modes dialogue/area become region). */
    var liveScope: String
        get() = sp.getString("live_scope", null).takeIf { it == "screen" } ?: "region"
        set(v) = sp.edit().putString("live_scope", v).apply()

    /** Game picked by hand in the bubble menu ("" = detect automatically). */
    var manualGame: String
        get() = sp.getString("manual_game", "") ?: ""
        set(v) = sp.edit().putString("manual_game", v).apply()

    /** The regions / Live mode above were moved into the default game profile (4b). */
    var profilesMigrated: Boolean
        get() = sp.getBoolean("profiles_migrated", false)
        set(v) = sp.edit().putBoolean("profiles_migrated", v).apply()

    /** Bubble panel mode: "once" (one press, one translation) or "live" (translate automatically). */
    var translateMode: String
        get() = sp.getString("translate_mode", "once") ?: "once"
        set(v) = sp.edit().putString("translate_mode", v).apply()

    var bubbleX: Int
        get() = sp.getInt("bubble_x", 0)
        set(v) = sp.edit().putInt("bubble_x", v).apply()

    var bubbleY: Int
        get() = sp.getInt("bubble_y", 400)
        set(v) = sp.edit().putInt("bubble_y", v).apply()
}
