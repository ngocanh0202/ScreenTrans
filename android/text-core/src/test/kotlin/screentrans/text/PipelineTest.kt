package screentrans.text

import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PipelineTest {
    private val shared = File(System.getProperty("shared.dir"))
    private val game = File(shared, "glossary/games/reverse1999.json").readText()

    private class FakeTranslator(val fn: (String) -> String) : SentenceTranslator {
        val calls = mutableListOf<List<String>>()
        override fun translate(texts: List<String>): List<String> {
            calls.add(texts)
            return texts.map { if (it.isBlank()) "" else fn(it) }
        }
    }

    private fun pipeline(tr: FakeTranslator, glossary: Glossary = Glossary(emptyList()), tracker: ProperNounTracker? = null) =
        Pipeline(tr, "fake", glossary, TranslationCache(100), tracker)

    private fun text(s: String, top: Float = 0f) = Paragraph(Kind.TEXT, s, Postprocess.splitSentences(s), 0f, top, 10f, top + 10f)
    private val name = Paragraph(Kind.NAME, "Druvis III", emptyList(), 0f, 0f, 10f, 10f)

    @Test
    fun `name not translated and one batch`() {
        val tr = FakeTranslator { "VI:$it" }
        val segs = pipeline(tr).translateParagraphs(listOf(name, text("One. Two.", 20f), text("Three.", 40f)))
        assertEquals(Kind.NAME, segs[0].kind)
        assertNull(segs[0].translation)
        assertEquals("VI:One. VI:Two.", segs[1].translation)
        assertEquals(listOf(listOf("One.", "Two.", "Three.")), tr.calls)
    }

    @Test
    fun `cache hit on second run`() {
        val tr = FakeTranslator { it.uppercase() }
        val p = pipeline(tr)
        p.translateParagraphs(listOf(text("Hi.")))
        p.translateParagraphs(listOf(text("Hi.")))
        assertEquals(1, tr.calls.size)
    }

    @Test
    fun `broken placeholder falls back and is not cached`() {
        val tr = FakeTranslator { it.replace("[0]", "") + " (vi)" }
        val p = pipeline(tr, Glossary.load(game))
        val seg = p.translateParagraphs(listOf(text("Hello Vertin.")))[0]
        assertEquals("Hello Vertin. (vi)", seg.translation)
        assertEquals(listOf("Hello Vertin."), tr.calls[1])
        p.translateParagraphs(listOf(text("Hello Vertin.")))
        assertEquals(4, tr.calls.size)
    }

    @Test
    fun `glossary terms survive`() {
        val tr = FakeTranslator { it.replace("Good morning", "Chào buổi sáng") }
        val seg = pipeline(tr, Glossary.load(game)).translateParagraphs(listOf(text("Good morning, Timekeeper.")))[0]
        assertEquals("Chào buổi sáng, Timekeeper.", seg.translation)
    }

    @Test
    fun `tracker adds proper noun after three distinct sentences`() {
        val g = Glossary(emptyList())
        val p = pipeline(FakeTranslator { it }, g, ProperNounTracker(emptySet(), 3))
        for (i in 0 until 3) p.translateParagraphs(listOf(text("Hello Sonetto number$i.")))
        assertEquals(listOf("Sonetto"), g.protect("Hi Sonetto.").second)
    }

    @Test
    fun `iter segments translates paragraph by paragraph`() {
        val tr = FakeTranslator { it.uppercase() }
        val it = pipeline(tr).iterSegments(listOf(name, text("One. Two.", 20f), text("Three.", 40f))).iterator()
        assertEquals(Kind.NAME, it.next().kind)
        assertTrue(tr.calls.isEmpty())
        assertEquals("ONE. TWO.", it.next().translation)
        assertEquals(listOf(listOf("One.", "Two.")), tr.calls)
        assertEquals("THREE.", it.next().translation)
        assertEquals(2, tr.calls.size)
    }

    @Test
    fun `split long keeps short text and cuts at punctuation then words`() {
        val words = { s: String -> s.split(" ").size }
        assertEquals(listOf("Hello there."), splitLong("Hello there.", words, 5))
        val text = "a b c, d e f, g h i j k l m n"
        val parts = splitLong(text, words, 4)
        assertEquals(text, parts.joinToString(" "))
        assertTrue(parts.all { it.split(" ").size <= 4 })
        assertEquals("a b c,", parts[0])
    }

    @Test
    fun `iterSentences yields after each sentence with an ellipsis for the rest`() {
        val tr = FakeTranslator { "VI:$it" }
        val steps = pipeline(tr).iterSentences(listOf(name, text("One. Two.", 20f))).toList()
        assertEquals(2, steps.size)
        assertEquals("VI:One. …", steps[0][1].translation)
        assertEquals("VI:One. VI:Two.", steps[1][1].translation)
        assertNull(steps[1][0].translation)
        assertEquals(listOf(listOf("One."), listOf("Two.")), tr.calls)
    }

    @Test
    fun `iterSentences yields once for no text`() {
        val steps = pipeline(FakeTranslator { it }).iterSentences(listOf(name)).toList()
        assertEquals(1, steps.size)
    }

    @Test
    fun `override wins over cache and model whatever the whitespace`() {
        val tr = FakeTranslator { "VI:$it" }
        val p = Pipeline(tr, "fake", Glossary(emptyList()), TranslationCache(100), overrides = mutableMapOf("Hello there." to "Chào cậu."))
        val segs = p.translateParagraphs(listOf(text("Hello  there.")))
        assertEquals("Chào cậu.", segs[0].translation)
        assertTrue(tr.calls.isEmpty())
    }

    @Test
    fun `correct is used next time and set game switches overrides`() {
        val tr = FakeTranslator { "VI:$it" }
        val p = pipeline(tr)
        assertEquals("VI:Run.", p.translateParagraphs(listOf(text("Run.")))[0].translation)
        p.correct("Run.", "Chạy đi!")
        assertEquals("Chạy đi!", p.translateParagraphs(listOf(text("Run.")))[0].translation)
        p.setGame(Glossary(emptyList()), mapOf("Go." to "Đi."))
        assertEquals("VI:Run.", p.translateParagraphs(listOf(text("Run.")))[0].translation)
        assertEquals("Đi.", p.translateParagraphs(listOf(text("Go.")))[0].translation)
    }

    @Test
    fun `cache namespace follows glossary edits and model version, not auto keep`() {
        val g = Glossary(emptyList())
        val p = Pipeline(FakeTranslator { it }, "fake", g, TranslationCache(100), modelVersion = "2")
        val ns = p.cacheNs
        assertTrue(ns.startsWith("fake@2#"))
        g.addKeep("Vertin")
        assertEquals(ns, p.cacheNs)
        g.addEntry("Arcanist", null)
        assertTrue(ns != p.cacheNs)
    }
}
