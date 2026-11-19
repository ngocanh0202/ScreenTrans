package dev.screentrans.core.live

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ThumbTest {
    private fun solid(w: Int, h: Int, argb: Int) = IntArray(w * h) { argb }

    @Test
    fun `same image gives zero`() {
        val a = Thumb.fromArgb(solid(640, 160, 0xFF336699.toInt()), 640, 160)
        assertEquals(160 * 40, a.size)  // 160 x 40 (keeps the aspect ratio)
        assertEquals(0f, Thumb.diff(a, a))
    }

    @Test
    fun `white vs black changes every cell`() {
        val w = Thumb.fromArgb(solid(128, 32, 0xFFFFFFFF.toInt()), 128, 32)
        val b = Thumb.fromArgb(solid(128, 32, 0xFF000000.toInt()), 128, 32)
        assertEquals(w.size.toFloat(), Thumb.diff(w, b))
    }

    @Test
    fun `a short line appearing on a full screen counts as a change`() {
        // regression: a mean over a 64-px thumbnail hid new dialogue (< 1), so Live only read the first line
        val (sw, sh) = 2048 to 942
        val screen = solid(sw, sh, 0xFF282C34.toInt())
        val talk = screen.copyOf()
        for (c in 0 until 3) for (y in 820 until 856) for (x in 600 + c * 24 until 600 + c * 24 + 4)
            talk[y * sw + x] = 0xFFEBEBEB.toInt()  // three 4-px strokes, 36 px tall
        val d = Thumb.diff(Thumb.fromArgb(screen, sw, sh), Thumb.fromArgb(talk, sw, sh))
        assertTrue(d > 5f, "diff $d")
        val flicker = IntArray(screen.size) { 0xFF2A2E36.toInt() }  // +2 grey levels everywhere
        assertTrue(Thumb.diff(Thumb.fromArgb(screen, sw, sh), Thumb.fromArgb(flicker, sw, sh)) <= 5f)
    }

    @Test
    fun `one noisy pixel stays under the threshold`() {
        val base = solid(640, 160, 0xFF000000.toInt())
        val noisy = base.copyOf().also { it[5000] = 0xFFFFFFFF.toInt() }
        val d = Thumb.diff(Thumb.fromArgb(base, 640, 160), Thumb.fromArgb(noisy, 640, 160))
        assertTrue(d < 5f, "diff $d")
    }

    @Test
    fun `different sizes never compare equal`() {
        val a = Thumb.fromArgb(solid(64, 16, 0), 64, 16)
        val b = Thumb.fromArgb(solid(64, 32, 0), 64, 32)
        assertEquals(Float.MAX_VALUE, Thumb.diff(a, b))
    }

    @Test
    fun `small images are not upscaled`() {
        assertEquals(10 * 5, Thumb.fromArgb(solid(10, 5, 0), 10, 5).size)
    }
}
