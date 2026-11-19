package screentrans.text

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Remote LLM hooks: same behaviour as windows/app/pipeline.py (tests in windows/tests/test_llm_translator.py). */
class PipelineRemoteTest {
    private class Local : SentenceTranslator {
        val calls = mutableListOf<List<String>>()
        override fun translate(texts: List<String>) = texts.map { "LOCAL $it" }.also { calls.add(texts) }
    }

    private open class FakeEngine(override val local: Local = Local()) : RemoteEngine {
        override val modelId = "gemini:x"
        override val localModelId = "opus"
        var up = true
        val calls = mutableListOf<Pair<List<String>, Map<String, String?>>>()
        var seenSpeaker: String? = "unset"
        var seenExamples: List<Pair<String, String>> = emptyList()
        override open fun translateCtx(texts: List<String>, glossary: Map<String, String?>): List<String>? {
            calls.add(texts to glossary)
            return if (up) texts.map { "LLM $it" } else null
        }
        override fun available() = up
        override fun setSpeaker(name: String?) { seenSpeaker = name }
        override fun setExamples(examples: List<Pair<String, String>>) { seenExamples = examples }
    }

    private val keep = Glossary(listOf(Entry("Druvis III", true, null, true)))
    private fun pipeline(e: FakeEngine) = Pipeline(e.local, "opus", keep, TranslationCache(100)).apply { setEngine(e) }
    private fun text(s: String, top: Float = 20f) = Paragraph(Kind.TEXT, s, Postprocess.splitSentences(s), 0f, top, 10f, top + 10f)
    private fun name(s: String, left: Float = 0f) = Paragraph(Kind.NAME, s, emptyList(), left, 0f, left + 10f, 10f)
    private val dialogue = listOf(name("Vertin"), text("Druvis III waits. We should go. Now."))

    @Test
    fun `glossary terms go to the engine without placeholders, with the speaker`() {
        val e = FakeEngine()
        val segs = pipeline(e).translateParagraphs(dialogue)
        assertEquals("LLM Druvis III waits. LLM We should go. LLM Now.", segs[1].translation)
        assertEquals(mapOf("Druvis III" to null), e.calls[0].second)
        assertEquals("Druvis III waits.", e.calls[0].first[0])
        assertEquals("Vertin", e.seenSpeaker)
    }

    @Test
    fun `live sentences use one call`() {
        val e = FakeEngine()
        val snaps = pipeline(e).iterSentences(dialogue).toList()
        assertEquals(1, e.calls.size)
        assertEquals(3, snaps.size)
    }

    @Test
    fun `live falls back sentence by sentence and caches under the local model`() {
        val e = FakeEngine().apply { up = false }
        val p = pipeline(e)
        assertEquals(3, p.iterSentences(dialogue).toList().size)
        assertEquals(listOf(1, 1, 1), e.local.calls.map { it.size })
        p.translateParagraphs(dialogue)  // still down: the local results come from the cache
        assertEquals(3, e.local.calls.size)
        e.up = true
        val segs = p.translateParagraphs(dialogue)  // back: the remote engine, not the cached local results
        assertEquals("LLM Druvis III waits. LLM We should go. LLM Now.", segs[1].translation)
    }

    @Test
    fun `a failing call translates locally`() {
        val e = object : FakeEngine() {
            override fun translateCtx(texts: List<String>, glossary: Map<String, String?>): List<String>? = null
        }
        val segs = pipeline(e).translateParagraphs(dialogue)
        assertTrue(segs[1].translation!!.startsWith("LOCAL "))
    }

    @Test
    fun `fullscreen sends a speaker only with a single name`() {
        val e = FakeEngine()
        val p = pipeline(e)
        p.iterSegments(dialogue).toList()
        assertEquals("Vertin", e.seenSpeaker)
        p.iterSegments(dialogue + listOf(name("Sonetto", 300f), text("Run.", 40f))).toList()
        assertNull(e.seenSpeaker)
    }

    @Test
    fun `corrections become examples, newest last, at most five`() {
        val e = FakeEngine()
        val p = pipeline(e)
        for (i in 1..7) p.correct("S$i.", "V$i.")
        p.correct("S3.", "V3 again.")
        assertEquals(listOf("S5." to "V5.", "S6." to "V6.", "S7." to "V7.", "S3." to "V3 again."),
            e.seenExamples.takeLast(4))
        assertEquals(5, e.seenExamples.size)
        assertEquals(e.seenExamples, p.examples())
    }

    @Test
    fun `terms in texts`() {
        assertEquals(mapOf("Druvis III" to null), keep.termsIn(listOf("Hi, Druvis III.")))
        assertFalse(keep.termsIn(listOf("Nobody.")).isNotEmpty())
    }

    @Test
    fun `live sentences use the given speaker`() {
        val e = FakeEngine()
        pipeline(e).iterSentences(listOf(text("Go.")), speaker = "Vertin").toList()
        assertEquals("Vertin", e.seenSpeaker)
    }
}
