package dev.screentrans.core.ui

/** How the bubble panel translates: one press = one translation, or automatic (Live). */
enum class TranslateMode(val key: String) {
    ONCE("once"), LIVE("live");

    companion object {
        fun parse(s: String?): TranslateMode = entries.firstOrNull { it.key == s } ?: ONCE
    }
}

enum class PanelAction { TRANSLATE_REGION, TRANSLATE_SCREEN, START_LIVE, STOP_LIVE }

/** What else must happen when a toggle of the panel changes. */
enum class PanelEffect { NONE, STOP_LIVE, RESTART_LIVE }

/** The bubble panel: two toggles (mode, scope), "Chọn vùng" and one main button that follows them. */
data class PanelState(val mode: TranslateMode, val screen: Boolean, val liveRunning: Boolean) {
    val chooseRegionEnabled: Boolean get() = !screen

    /** The main button: what it does and its label. */
    val primary: Pair<PanelAction, String>
        get() = when (mode) {
            TranslateMode.ONCE -> if (screen) PanelAction.TRANSLATE_SCREEN to "Dịch màn hình" else PanelAction.TRANSLATE_REGION to "Dịch vùng"
            TranslateMode.LIVE -> if (liveRunning) PanelAction.STOP_LIVE to "Tắt tự động dịch" else PanelAction.START_LIVE to "Bật tự động dịch"
        }

    fun onModeChanged(newMode: TranslateMode): PanelEffect =
        if (liveRunning && newMode == TranslateMode.ONCE) PanelEffect.STOP_LIVE else PanelEffect.NONE

    fun onScopeChanged(screen: Boolean): PanelEffect =
        if (liveRunning && screen != this.screen) PanelEffect.RESTART_LIVE else PanelEffect.NONE
}
