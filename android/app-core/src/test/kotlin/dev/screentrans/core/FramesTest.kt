package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FramesTest {
    private val black = 0xFF000000.toInt()
    private val white = 0xFFFFFFFF.toInt()

    @Test
    fun `all black frame is a blocked capture`() {
        assertTrue(Frames.isMostlyBlack(IntArray(10_000) { black }))
    }

    @Test
    fun `five percent bright pixels is a real frame`() {
        assertFalse(Frames.isMostlyBlack(IntArray(10_000) { if (it % 20 == 0) white else black }))
    }

    @Test
    fun `dark but not black game scene is not blocked`() {
        val darkGrey = 0xFF202020.toInt()
        assertFalse(Frames.isMostlyBlack(IntArray(10_000) { darkGrey }))
    }

    @Test
    fun `clamp keeps rect inside image`() {
        assertContentEquals(intArrayOf(900, 700, 1000, 800), Frames.clampRect(1000, 800, 900, 700, 1200, 900))
        assertContentEquals(intArrayOf(0, 0, 50, 40), Frames.clampRect(1000, 800, -20, -10, 50, 40))
    }

    @Test
    fun `rect outside image is empty`() {
        val r = Frames.clampRect(1000, 800, 1100, 900, 1200, 1000)
        assertTrue(r[2] <= r[0] || r[3] <= r[1])
    }
}
