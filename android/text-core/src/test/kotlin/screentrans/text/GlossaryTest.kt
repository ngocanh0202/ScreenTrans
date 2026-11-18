package screentrans.text

import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertNull

class GlossaryTest {
    private val shared = File(System.getProperty("shared.dir"))
    private val common = File(shared, "glossary/common.json").readText()
    private val game = File(shared, "glossary/games/reverse1999.json").readText()
    private fun json(vararg entries: String) = """{"version": 1, "entries": [${entries.joinToString(",")}]}"""

    @Test
    fun `keep round trip`() {
        val g = Glossary.load(game, common)
        val (text, values) = g.protect("Good morning, Timekeeper. Your HP is low.")
        assertEquals(listOf("Timekeeper", "HP"), values)
        val translated = text.replace("Good morning", "Chào buổi sáng").replace("Your", "Của bạn")
        assertEquals("Chào buổi sáng, Timekeeper. Của bạn HP is low.", g.restore(translated, values))
    }

    @Test
    fun `map entry restores target`() {
        val g = Glossary.load(json("""{"source": "Arcanist", "type": "map", "target": "Thuật sĩ"}"""))
        val (text, values) = g.protect("The Arcanist waits.")
        assertEquals(listOf("Thuật sĩ"), values)
        assertEquals("The Thuật sĩ waits.", g.restore(text, values))
    }

    @Test
    fun `game glossary wins over common`() {
        val g = Glossary.load(json("""{"source": "HP", "type": "map", "target": "Máu"}"""), common)
        assertEquals(listOf("Máu"), g.protect("HP low").second)
    }

    @Test
    fun `longest match first and word boundaries`() {
        assertEquals(listOf("Druvis III", "Vertin"), Glossary.load(game).protect("Druvis III smiled at Vertin.").second)
        assertEquals(emptyList(), Glossary.load(common).protect("HPX and shape").second)
    }

    @Test
    fun `case insensitive entry and case sensitive default`() {
        val g = Glossary.load(json("""{"source": "timekeeper", "type": "keep", "case_sensitive": false}"""))
        assertEquals(listOf("TIMEKEEPER"), g.protect("TIMEKEEPER!").second)
        assertEquals(emptyList(), Glossary.load(game).protect("the vertin").second)
    }

    @Test
    fun `restore detects dropped or renumbered placeholders`() {
        val g = Glossary.load(game)
        val (text, values) = g.protect("Hello Vertin and Sonetto.")
        assertNull(g.restore(text.replace("[1]", ""), values))
        assertNull(g.restore(text.replace("[0]", "[7]"), values))
    }

    @Test
    fun `add keep and priority rules`() {
        val g = Glossary.load(common)
        g.addKeep("Bob")
        assertEquals(listOf("Bob"), g.protect("Hi Bob.").second)
        val folded = Glossary.load(json("""{"source": "arcanist", "type": "map", "target": "Thuật sư", "case_sensitive": false}"""))
        folded.addKeep("Arcanist")
        assertEquals(listOf("Thuật sư"), folded.protect("The Arcanist waits.").second)
        val hp = Glossary.load(json("""{"source": "hp", "type": "map", "target": "Máu", "case_sensitive": false}"""), common)
        assertEquals(listOf("Máu"), hp.protect("HP low").second)
    }

    @Test
    fun `proper noun tracker counts distinct sentences`() {
        val words = File(shared, "glossary/common_words_en.txt").readLines().map { it.trim().lowercase() }.toSet()
        val t = ProperNounTracker(words, minCount = 3)
        repeat(5) { assertEquals(emptyList(), t.observe("Hello Sonetto.")) }
        assertEquals(emptyList(), t.observe("Thanks Sonetto."))
        assertEquals(listOf("Sonetto"), t.observe("Bye Sonetto."))
        assertEquals(emptyList(), t.observe("Again Sonetto."))
        assertEquals(emptyList(), ProperNounTracker(words, 1).observe("The cat likes Water."))
    }
}
