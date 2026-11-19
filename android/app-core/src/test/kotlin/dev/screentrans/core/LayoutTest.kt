package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertTrue

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

    @Test
    fun `live card goes above its region and avoids every watched region`() {
        val name = intArrayOf(0, 500, 300, 560)
        val dialogue = intArrayOf(0, 600, 1000, 800)
        // above the dialogue box would cover the name plate region -> below instead
        assertEquals(listOf(0, 812), Layout.placeOutside(dialogue, 600, 100, 1080, 2400, listOf(name, dialogue))!!.toList())
        // plain case: above
        assertEquals(listOf(0, 488), Layout.placeOutside(dialogue, 600, 100, 1080, 2400, listOf(dialogue))!!.toList())
        // nowhere outside: null (caller hides the card while capturing)
        val full = intArrayOf(0, 50, 1080, 2350)
        assertEquals(null, Layout.placeOutside(full, 600, 100, 1080, 2400, listOf(full)))
    }

    @Test
    fun `a long translation grows the box before the font shrinks, then reports truncation`() {
        // 40 px font, 400 px wide box of one 50 px line: ~18 chars per line
        val short = Layout.fitBlock(10, 400, 50, 40f, maxH = 1000, grow = true)
        assertEquals(40f, short.px); assertEquals(false, short.truncated)
        val long = Layout.fitBlock(90, 400, 50, 40f, maxH = 1000, grow = true)  // 5 lines: needs 250 px > 1.5x
        assertEquals(40f, long.px); assertTrue(long.height in 151..450); assertEquals(false, long.truncated)
        val shrink = Layout.fitBlock(90, 400, 50, 40f, maxH = 1000, grow = false)
        assertTrue(shrink.px < 40f); assertTrue(shrink.height <= 75)
        val huge = Layout.fitBlock(2000, 400, 50, 40f, maxH = 120, grow = true)
        assertEquals(true, huge.truncated); assertTrue(huge.height <= 150)
    }

    @Test
    fun `text scale steps`() {
        assertEquals(1.25f, Layout.nextScale(1f))
        assertEquals(0.8f, Layout.prevScale(1f))
        assertEquals(1.5f, Layout.nextScale(1.5f))
        assertEquals(0.8f, Layout.prevScale(0.8f))
    }

    @Test
    fun `the expand button sits at the real bottom-right corner of a tilted box, inside the screen`() {
        // a 300 x 60 box at (100, 200) in a frame tilted 20 degrees around (0, 0)
        val (x, y) = Layout.cornerOnScreen(floatArrayOf(100f, 200f, 400f, 260f), 20f, size = 40, screenW = 1080, screenH = 2400)
        val cx = (400 * Math.cos(Math.toRadians(20.0)) - 260 * Math.sin(Math.toRadians(20.0))).toFloat()
        val cy = (400 * Math.sin(Math.toRadians(20.0)) + 260 * Math.cos(Math.toRadians(20.0))).toFloat()
        assertEquals((cx - 40).toInt(), x); assertEquals((cy - 20).toInt(), y)
        val (ex, ey) = Layout.cornerOnScreen(floatArrayOf(900f, 2300f, 1200f, 2420f), 0f, size = 40, screenW = 1080, screenH = 2400)
        assertEquals(1040, ex); assertEquals(2360, ey)  // clamped inside the screen
    }

    @Test
    fun `live translation starts a little above the source line`() {
        assertEquals(94f, Layout.liftedTop(100f, 30f, tilted = false))  // 20 % of the text size
        assertEquals(0f, Layout.liftedTop(2f, 30f, tilted = false))     // never above the screen
        assertEquals(-4f, Layout.liftedTop(2f, 30f, tilted = true))     // tilted frame: coordinates may be negative
    }
}
