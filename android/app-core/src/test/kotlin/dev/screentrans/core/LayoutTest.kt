package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals

class LayoutTest {
    @Test
    fun `below the region`() {
        assertContentEquals(intArrayOf(100, 192), Layout.placeOverlay(intArrayOf(100, 100, 500, 180), 400, 120, 1920, 1080))
    }

    @Test
    fun `above when the bottom overflows`() {
        assertContentEquals(intArrayOf(100, 868), Layout.placeOverlay(intArrayOf(100, 1000, 500, 1060), 400, 120, 1920, 1080))
    }

    @Test
    fun `clamped to the right edge`() {
        assertEquals(1520, Layout.placeOverlay(intArrayOf(1800, 100, 1900, 150), 400, 120, 1920, 1080)[0])
    }

    @Test
    fun `no room above or below sticks to the bottom inside`() {
        assertEquals(960, Layout.placeOverlay(intArrayOf(0, 0, 400, 1080), 400, 120, 1920, 1080)[1])
    }

    @Test
    fun `short text keeps the base size, very long text shrinks to the minimum`() {
        assertEquals(40f, Layout.fitTextPx(2, 200, 40, 40f))
        assertEquals(Layout.MIN_TEXT_PX, Layout.fitTextPx(2000, 120, 20, 40f))
        assertEquals(12f, Layout.fitTextPx(2000, 120, 20, 12f))  // base already below the minimum
    }

    @Test
    fun `medium text shrinks between base and minimum`() {
        val size = Layout.fitTextPx(60, 300, 40, 32f)
        assert(size < 32f && size >= Layout.MIN_TEXT_PX)
    }
}

class BubbleClampTest {
    @Test
    fun `bubble saved in portrait is pulled back onto a landscape screen`() {
        assertContentEquals(intArrayOf(0, 948), Layout.clampBubble(0, 1800, 132, 2400, 1080))
        assertContentEquals(intArrayOf(0, 948), Layout.clampBubble(-50, 1800, 132, 2400, 1080))
        assertContentEquals(intArrayOf(2268, 10), Layout.clampBubble(2500, 10, 132, 2400, 1080))
        assertContentEquals(intArrayOf(100, 200), Layout.clampBubble(100, 200, 132, 2400, 1080))
    }
}
