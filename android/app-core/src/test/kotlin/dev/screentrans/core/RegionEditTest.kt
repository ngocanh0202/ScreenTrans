package dev.screentrans.core

import org.junit.jupiter.api.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RegionEditTest {
    private val rects = listOf(intArrayOf(100, 100, 500, 300), intArrayOf(100, 600, 500, 800))

    @Test
    fun `hit test finds corners, body and nothing`() {
        assertEquals(RegionEdit.Hit(0, RegionEdit.Part.TOP_LEFT), RegionEdit.hitTest(rects, 105, 95, 40))
        assertEquals(RegionEdit.Hit(1, RegionEdit.Part.BOTTOM_RIGHT), RegionEdit.hitTest(rects, 495, 810, 40))
        assertEquals(RegionEdit.Hit(1, RegionEdit.Part.BODY), RegionEdit.hitTest(rects, 300, 700, 40))
        assertNull(RegionEdit.hitTest(rects, 900, 900, 40))
    }

    @Test
    fun `dragging a corner resizes, the body moves`() {
        val r = intArrayOf(100, 100, 500, 300)
        assertContentEquals(intArrayOf(100, 100, 600, 350), RegionEdit.drag(r, RegionEdit.Part.BOTTOM_RIGHT, 100, 50, 1000, 1000))
        assertContentEquals(intArrayOf(50, 80, 500, 300), RegionEdit.drag(r, RegionEdit.Part.TOP_LEFT, -50, -20, 1000, 1000))
        assertContentEquals(intArrayOf(150, 120, 550, 320), RegionEdit.drag(r, RegionEdit.Part.BODY, 50, 20, 1000, 1000))
    }

    @Test
    fun `moving keeps the size inside the screen and resizing keeps a minimum size`() {
        val r = intArrayOf(100, 100, 500, 300)
        assertContentEquals(intArrayOf(600, 800, 1000, 1000), RegionEdit.drag(r, RegionEdit.Part.BODY, 900, 900, 1000, 1000))
        val tiny = RegionEdit.drag(r, RegionEdit.Part.BOTTOM_RIGHT, -1000, -1000, 1000, 1000)
        assertContentEquals(intArrayOf(100, 100, 100 + RegionEdit.MIN_SIZE, 100 + RegionEdit.MIN_SIZE), tiny)
    }

    @Test
    fun `region list serializes and old single region still loads`() {
        val list = listOf(RelRect(0.1f, 0.1f, 0.5f, 0.2f), RelRect(0.2f, 0.6f, 0.9f, 0.8f))
        assertEquals(list, RelRect.parseList(RelRect.serializeList(list)))
        assertEquals(listOf(RelRect(0.1f, 0.1f, 0.5f, 0.2f)), RelRect.parseList("0.1,0.1,0.5,0.2"))
        assertEquals(emptyList(), RelRect.parseList(null))
        assertEquals(emptyList(), RelRect.parseList("junk"))
    }
}
