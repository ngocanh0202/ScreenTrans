package dev.screentrans.core.live

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ThumbTest {
    private fun solid(w: Int, h: Int, argb: Int) = IntArray(w * h) { argb }

    @Test
    fun `same image gives zero`() {
        val a = Thumb.fromArgb(solid(200, 50, 0xFF336699.toInt()), 200, 50)
        assertEquals(64, a.size / 16)  // 64 x 16 (keeps the aspect ratio)
        assertEquals(0f, Thumb.diff(a, a))
    }

    @Test
    fun `white vs black gives 255`() {
        val w = Thumb.fromArgb(solid(128, 32, 0xFFFFFFFF.toInt()), 128, 32)
        val b = Thumb.fromArgb(solid(128, 32, 0xFF000000.toInt()), 128, 32)
        assertEquals(255f, Thumb.diff(w, b), 0.5f)
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
