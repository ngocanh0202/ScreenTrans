package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RelRectTest {
    @Test
    fun `from pixels to fractions`() {
        val r = RelRect.fromPx(100, 200, 500, 400, 1000, 2000)
        assertEquals(RelRect(0.1f, 0.1f, 0.5f, 0.2f), r)
    }

    @Test
    fun `back to pixels on a rotated screen keeps proportions`() {
        val r = RelRect(0.1f, 0.1f, 0.5f, 0.2f)
        assertContentEquals(intArrayOf(100, 200, 500, 400), r.toPx(1000, 2000))
        assertContentEquals(intArrayOf(200, 100, 1000, 200), r.toPx(2000, 1000))
    }

    @Test
    fun `drag in any direction is normalized and clamped`() {
        assertEquals(RelRect(0.1f, 0.1f, 0.5f, 0.2f), RelRect.fromPx(500, 400, 100, 200, 1000, 2000))
        assertEquals(RelRect(0f, 0f, 1f, 1f), RelRect.fromPx(-50, -50, 1200, 2500, 1000, 2000))
    }

    @Test
    fun `usable needs at least 8 px each way`() {
        assertTrue(RelRect.fromPx(0, 0, 8, 8, 1000, 1000).isUsable(1000, 1000))
        assertFalse(RelRect.fromPx(0, 0, 5, 100, 1000, 1000).isUsable(1000, 1000))
    }

    @Test
    fun `serializes to and from a string`() {
        val r = RelRect(0.1f, 0.25f, 0.5f, 0.75f)
        assertEquals(r, RelRect.parse(r.serialize()))
        assertEquals(null, RelRect.parse("garbage"))
    }
}
