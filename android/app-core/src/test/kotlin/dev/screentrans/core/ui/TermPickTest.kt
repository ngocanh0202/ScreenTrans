package dev.screentrans.core.ui

import org.junit.jupiter.api.Test
import screentrans.text.Terms
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class TermPickTest {
    private val sentences = listOf(
        Terms.tokens("Ms. Z, please walk Madam Constantine through this section."),
        Terms.tokens("Druvis III is here."),
    )

    @Test
    fun `tap selects a word, a second tap extends, tapping the single word again clears`() {
        val sel = WordSelection()
        sel.tap(0, 4)
        assertEquals("Madam", sel.text(sentences))
        sel.tap(0, 5)
        assertEquals("Madam Constantine", sel.text(sentences))
        assertTrue(sel.isSelected(0, 4) && sel.isSelected(0, 5) && !sel.isSelected(0, 3))
        sel.tap(0, 1)  // extends from the first tapped word
        assertEquals("Z, please walk Madam", sel.text(sentences))
        sel.clear()
        sel.tap(0, 5)
        sel.tap(0, 5)
        assertEquals("", sel.text(sentences))
    }

    @Test
    fun `a tap in another sentence starts a new selection there`() {
        val sel = WordSelection()
        sel.tap(0, 4)
        sel.tap(1, 0)
        sel.tap(1, 1)
        assertEquals("Druvis III", sel.text(sentences))
        assertFalse(sel.isSelected(0, 4))
    }

    @Test
    fun `term list replaces the same source in any case and removes`() {
        val terms = TermList()
        terms.add("Madam Constantine", null)
        terms.add("madam constantine", "Phu nhân Constantine")
        terms.add("Druvis III", null)
        assertEquals(listOf("madam constantine" to "Phu nhân Constantine", "Druvis III" to null), terms.items)
        terms.remove("Druvis III")
        assertEquals(1, terms.items.size)
        terms.add("  ", null)
        assertEquals(1, terms.items.size)
    }

    @Test
    fun `model names equal to the default are not stored`() {
        val m = LlmPrefsLogic.models(mapOf("openai" to "gpt-x"), "gemini", "  gemini-2.5-flash ")
        assertEquals(mapOf("openai" to "gpt-x"), m)
        assertEquals(mapOf("openai" to "gpt-x", "gemini" to "gemini-2.5-pro"), LlmPrefsLogic.models(m, "gemini", "gemini-2.5-pro"))
        assertEquals(emptyMap(), LlmPrefsLogic.models(mapOf("openai" to "gpt-x"), "openai", ""))
    }
}
