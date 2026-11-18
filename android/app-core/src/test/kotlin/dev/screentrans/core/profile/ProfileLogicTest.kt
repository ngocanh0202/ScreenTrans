package dev.screentrans.core.profile

import dev.screentrans.core.RelRect
import org.junit.jupiter.api.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals

class ProfileLogicTest {
    @Test
    fun `manual choice wins, then the foreground app, never our own app`() {
        assertEquals("b.game", ProfileLogic.pickGame("a.game", "b.game", "dev.screentrans"))
        assertEquals("a.game", ProfileLogic.pickGame("a.game", null, "dev.screentrans"))
        assertEquals(Profile.DEFAULT_ID, ProfileLogic.pickGame("dev.screentrans", null, "dev.screentrans"))
        assertEquals(Profile.DEFAULT_ID, ProfileLogic.pickGame(null, "", "dev.screentrans"))
    }

    @Test
    fun `phase 3-4a prefs become the default profile`() {
        val p = ProfileLogic.migratePrefs(listOf(RelRect(0.1f, 0.7f, 0.9f, 0.95f)), "area")
        assertEquals(Profile.DEFAULT_ID, p.id)
        assertEquals("region", p.scope)
        assertEquals(listOf(RelRect(0.1f, 0.7f, 0.9f, 0.95f)), ProfileLogic.regionsOf(p))
        assertEquals("screen", ProfileLogic.migratePrefs(emptyList(), "screen").scope)
    }

    @Test
    fun `regions round trip between profile x y w h and RelRect l t r b`() {
        val rects = listOf(RelRect(0.25f, 0.5f, 0.75f, 1f))
        val p = ProfileLogic.withRegions(Profile("g"), rects)
        assertEquals(listOf(listOf(0.25, 0.5, 0.5, 0.5)), p.regions)
        assertEquals(rects, ProfileLogic.regionsOf(p))
        assertEquals(rects, ProfileLogic.ignoreOf(ProfileLogic.withIgnore(Profile("g"), rects)))
    }

    @Test
    fun `ignore mask hides the ignored part of a region thumbnail`() {
        // region 0..640 x 0..160 -> thumbnail 4 x 1; ignore the right half
        val m = ProfileLogic.ignoreMask(intArrayOf(0, 0, 640, 160), listOf(intArrayOf(320, 0, 640, 160)), 4, 1)
        assertContentEquals(booleanArrayOf(true, true, false, false), m)
        val all = ProfileLogic.ignoreMask(intArrayOf(0, 0, 640, 160), listOf(intArrayOf(0, 0, 640, 160)), 4, 1)
        assertContentEquals(BooleanArray(4), all)
    }
}
