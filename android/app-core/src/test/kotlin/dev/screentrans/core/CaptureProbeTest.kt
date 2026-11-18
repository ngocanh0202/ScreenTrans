package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class CaptureProbeTest {
    private val magenta = 0xFFFF00FF.toInt()
    private val game = 0xFF204060.toInt()

    @Test
    fun `probe square found in the frame means overlays are captured`() {
        val px = IntArray(100) { game }
        for (i in 0 until 50) px[i] = magenta
        assertEquals(CaptureProbe.Verdict.OVERLAY_CAPTURED, CaptureProbe.verdict(px, magenta))
    }

    @Test
    fun `game pixels only means overlays are not captured`() {
        assertEquals(CaptureProbe.Verdict.OVERLAY_HIDDEN, CaptureProbe.verdict(IntArray(100) { game }, magenta))
    }

    @Test
    fun `a slightly different shade still counts as the probe`() {
        val px = IntArray(100) { 0xFFF00AF5.toInt() }
        assertEquals(CaptureProbe.Verdict.OVERLAY_CAPTURED, CaptureProbe.verdict(px, magenta))
    }

    @Test
    fun `black frame means the chosen app is not on screen`() {
        assertEquals(CaptureProbe.Verdict.BLACK, CaptureProbe.verdict(IntArray(100) { 0xFF000000.toInt() }, magenta))
    }
}
