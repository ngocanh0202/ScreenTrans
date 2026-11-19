package dev.screentrans.core.ui

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PanelStateTest {
    @Test
    fun `choose region is enabled only for the region scope`() {
        assertTrue(PanelState(TranslateMode.ONCE, screen = false, liveRunning = false).chooseRegionEnabled)
        assertFalse(PanelState(TranslateMode.ONCE, screen = true, liveRunning = false).chooseRegionEnabled)
        assertFalse(PanelState(TranslateMode.LIVE, screen = true, liveRunning = true).chooseRegionEnabled)
    }

    @Test
    fun `the main button follows mode, scope and whether live runs`() {
        assertEquals(PanelAction.TRANSLATE_REGION to "Dịch vùng", PanelState(TranslateMode.ONCE, false, false).primary)
        assertEquals(PanelAction.TRANSLATE_SCREEN to "Dịch màn hình", PanelState(TranslateMode.ONCE, true, false).primary)
        assertEquals(PanelAction.START_LIVE to "Bắt đầu dịch", PanelState(TranslateMode.LIVE, false, false).primary)
        assertEquals(PanelAction.STOP_LIVE to "Ngừng dịch", PanelState(TranslateMode.LIVE, true, true).primary)
    }

    @Test
    fun `switching to one-shot stops live, switching scope restarts it`() {
        val running = PanelState(TranslateMode.LIVE, screen = false, liveRunning = true)
        assertEquals(PanelEffect.STOP_LIVE, running.onModeChanged(TranslateMode.ONCE))
        assertEquals(PanelEffect.NONE, running.onModeChanged(TranslateMode.LIVE))
        assertEquals(PanelEffect.RESTART_LIVE, running.onScopeChanged(screen = true))
        assertEquals(PanelEffect.NONE, running.onScopeChanged(screen = false))
        assertEquals(PanelEffect.NONE, PanelState(TranslateMode.ONCE, false, false).onScopeChanged(true))
    }

    @Test
    fun `mode survives as text in the prefs`() {
        assertEquals(TranslateMode.LIVE, TranslateMode.parse("live"))
        assertEquals(TranslateMode.ONCE, TranslateMode.parse(null))
        assertEquals(TranslateMode.ONCE, TranslateMode.parse("junk"))
        assertEquals("live", TranslateMode.LIVE.key)
    }
}
