package dev.screentrans.core.llm

import com.google.gson.JsonParser
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import screentrans.text.SentenceTranslator
import java.io.File
import java.time.LocalDate
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Same cases as windows/tests/test_llm_translator.py (translator part). */
class LlmTranslatorTest {
    @TempDir
    lateinit var dir: File

    private open class FakeClient(var error: Exception? = null, var reply: String? = null) : LlmClient {
        override val name = "Gemini"
        override val model = "gemini-x"
        val calls = mutableListOf<Triple<String, String, Int>>()
        override fun complete(system: String, user: String, timeoutMs: Int): String {
            calls.add(Triple(system, user, timeoutMs))
            error?.let { throw it }
            reply?.let { return it }
            val sentences = JsonParser.parseString(user.substringAfterLast("\n")).asJsonArray.map { it.asString }
            return com.google.gson.Gson().toJson(mapOf("translations" to sentences.map { "LLM $it" }))
        }
    }

    private class Clock(var t: Long = 1_000_000) : () -> Long {
        override fun invoke() = t
    }

    private val local = SentenceTranslator { texts -> texts.map { "LOCAL $it" } }

    private fun make(client: LlmClient = FakeClient(), limit: Int = 50_000, clock: Clock = Clock(),
                     day: Array<LocalDate> = arrayOf(LocalDate.of(2026, 11, 19))): Pair<LlmTranslator, MutableList<String>> {
        val notes = mutableListOf<String>()
        val tr = LlmTranslator("gemini", client, local, "opus", UsageStore(dir) { day[0] }, limit, { notes.add(it) },
            clock, ContextStore(dir))
        return tr to notes
    }

    @Test
    fun `model id, context, speaker, glossary and timeout`() {
        val c = FakeClient()
        val (tr, _) = make(c)
        assertEquals("gemini:gemini-x", tr.modelId)
        tr.timeoutMs = 2500
        assertEquals(listOf("LLM Hello.", "LLM Bye."), tr.translateCtx(listOf("Hello.", "Bye."), emptyMap()))
        tr.setSpeaker("Vertin")
        tr.translateCtx(listOf("Druvis III is here."), mapOf("Druvis III" to null))
        val (_, user, timeout) = c.calls.last()
        assertEquals(2500, timeout)
        assertTrue("- Hello.\n- Bye." in user && "Người nói: Vertin" in user && "- Druvis III (giữ nguyên)" in user)
    }

    @Test
    fun `failure falls back once, then waits 30 s`() {
        val clock = Clock()
        val c = FakeClient(error = RemoteError("timeout", "Gemini"))
        val (tr, notes) = make(c, clock = clock)
        assertNull(tr.translateCtx(listOf("Hi."), emptyMap()))
        assertNull(tr.translateCtx(listOf("Yo."), emptyMap()))
        assertEquals(1, c.calls.size); assertEquals(1, notes.size)
        assertTrue("Gemini" in notes[0] && "model trên máy" in notes[0])
        clock.t += 31_000
        c.error = null
        assertEquals(listOf("LLM Hi."), tr.translateCtx(listOf("Hi."), emptyMap()))
    }

    @Test
    fun `wrong key blocks until set game`() {
        val c = FakeClient(error = RemoteError("auth", "Gemini"))
        val clock = Clock()
        val (tr, notes) = make(c, clock = clock)
        assertNull(tr.translateCtx(listOf("Hi."), emptyMap()))
        clock.t += 3_600_000
        assertNull(tr.translateCtx(listOf("Hi."), emptyMap()))
        assertEquals(1, c.calls.size)
        assertTrue("key" in notes[0] && "Cài đặt" in notes[0])
        assertFalse(tr.available())
        c.error = null
        tr.setGame("a", "", emptyList())
        assertTrue(tr.available())
    }

    @Test
    fun `daily limit, counted before the call, notice again after midnight`() {
        val day = arrayOf(LocalDate.of(2026, 11, 19))
        val c = FakeClient(error = RemoteError("timeout", "Gemini"))
        val (tr, notes) = make(c, limit = 10, day = day)
        tr.translateCtx(listOf("Hello."), emptyMap())  // 6 chars, counted although it failed
        val (tr2, notes2) = make(FakeClient(), limit = 10, day = day)
        assertNull(tr2.translateCtx(listOf("Goodbye."), emptyMap()))  // 6 + 8 > 10
        assertNull(tr2.translateCtx(listOf("Goodbye."), emptyMap()))
        assertEquals(1, notes2.size); assertTrue("giới hạn" in notes2[0])
        day[0] = LocalDate.of(2026, 11, 20)
        assertEquals(listOf("LLM Goodbye."), tr2.translateCtx(listOf("Goodbye."), emptyMap()))
        assertEquals(1, notes.size)
    }

    @Test
    fun `unusable reply goes local for that batch only`() {
        val c = FakeClient(reply = """{"translations": ["Một."]}""")
        val (tr, _) = make(c)
        assertNull(tr.translateCtx(listOf("One.", "Two."), emptyMap()))
        c.reply = null
        assertEquals(listOf("LLM One.", "LLM Two."), tr.translateCtx(listOf("One.", "Two."), emptyMap()))
    }

    @Test
    fun `any other exception falls back without showing its text`() {
        val (tr, notes) = make(FakeClient(error = IllegalStateException("Bearer sk-SECRET")))
        assertNull(tr.translateCtx(listOf("Hi."), emptyMap()))
        assertEquals(1, notes.size); assertFalse("sk-SECRET" in notes[0])
    }

    @Test
    fun `the timeout caps the whole call`() {
        val slow = object : FakeClient() {
            override fun complete(system: String, user: String, timeoutMs: Int): String {
                Thread.sleep(1500)
                return super.complete(system, user, timeoutMs)
            }
        }
        val (tr, notes) = make(slow)
        tr.timeoutMs = 300
        val t0 = System.nanoTime()
        assertNull(tr.translateCtx(listOf("Hi."), emptyMap()))
        assertTrue((System.nanoTime() - t0) / 1_000_000 < 1000)
        assertTrue("quá thời gian" in notes[0])
    }

    @Test
    fun `context, notes and examples are per game and saved`() {
        val c = FakeClient()
        val (tr, _) = make(c)
        tr.setGame("a.pkg", "Game A notes.", listOf("Hi." to "Chào em."))
        tr.setSpeaker("Vertin")
        tr.translateCtx(listOf("Line A."), emptyMap())
        tr.setGame("b.pkg", "", emptyList())
        tr.translateCtx(listOf("Line B."), emptyMap())
        val userB = c.calls.last().second
        assertFalse("Line A." in userB || "Game A notes." in userB || "Chào em." in userB)
        val (tr2, _) = make(c)  // the app restarted
        tr2.setGame("a.pkg", "Game A notes.", listOf("Hi." to "Chào em."))
        tr2.translateCtx(listOf("Next."), emptyMap())
        val user = c.calls.last().second
        assertTrue("Về game:\nGame A notes." in user && "- Hi. → Chào em." in user && "- Vertin: Line A." in user)
    }

    @Test
    fun `unsafe game ids and corrupt context files`() {
        val store = ContextStore(dir)
        val game = "C:\\games\\x?.pkg"
        store.save(game, listOf(null to "One."))
        assertEquals(listOf<Pair<String?, String>>(null to "One."), store.load(game))
        File(dir, "llm_context").listFiles()!!.single().writeText("{broken")
        assertEquals(emptyList(), store.load(game))
    }

    @Test
    fun `a locked usage file does not fail the job`() {
        val usage = object : UsageStore(dir, { LocalDate.of(2026, 11, 19) }) {
            override fun add(chars: Int) = throw java.io.IOException("locked")
        }
        val tr = LlmTranslator("gemini", FakeClient(), local, "opus", usage, 50_000, {}, Clock(), null)
        assertEquals(listOf("LLM Hi."), tr.translateCtx(listOf("Hi."), emptyMap()))
    }

    @Test
    fun `at most two calls run at once, a third counts as a timeout`() {
        val gate = java.util.concurrent.CountDownLatch(1)
        val started = java.util.concurrent.atomic.AtomicInteger()
        val stuck = object : FakeClient() {
            override fun complete(system: String, user: String, timeoutMs: Int): String {
                started.incrementAndGet()
                while (true) {  // like a blocked socket read / DNS lookup: an interrupt does not free the thread
                    try { gate.await(); break } catch (e: InterruptedException) { }
                }
                return super.complete(system, user, timeoutMs)
            }
        }
        val clock = Clock()
        val (tr, _) = make(stuck, clock = clock)
        tr.timeoutMs = 50
        repeat(3) {
            assertNull(tr.translateCtx(listOf("Hi $it."), emptyMap()))
            clock.t += 31_000  // past the back-off
        }
        Thread.sleep(100)
        assertEquals(2, started.get())  // the pool is bounded like Python (max_workers=2)
        gate.countDown()
    }
}
