package dev.screentrans.core.llm

import com.google.gson.JsonParser
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import screentrans.text.SentenceTranslator
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

class LlmEnginesTest {
    @TempDir
    lateinit var dir: File

    class Echo(override val model: String) : LlmClient {
        override val name = "Gemini"
        val users = mutableListOf<String>()
        val timeouts = mutableListOf<Int>()
        override fun complete(system: String, user: String, timeoutMs: Int): String {
            users.add(user)
            timeouts.add(timeoutMs)
            val s = JsonParser.parseString(user.substringAfterLast("\n")).asJsonArray.map { it.asString }
            return com.google.gson.Gson().toJson(mapOf("translations" to s.map { "LLM $it" }))
        }
    }

    private val keys = HashMap<String, String>()
    private val made = mutableListOf<Pair<String, Echo>>()
    private val notes = mutableListOf<String>()
    private val engines by lazy {
        LlmEngines(dir, { keys[it] ?: "" }, SentenceTranslator { t -> t.map { "LOCAL $it" } }, "opus",
            clientFactory = { engine, key, model, _ -> Echo(model.ifEmpty { "default" }).also { made.add(key to it) } })
            .also { it.notify = { m -> notes.add(m) } }
    }

    @Test
    fun `local or no key gives no remote engine, a missing key is told once`() {
        assertNull(engines.use("g", "local", LlmSettings(), emptyList()))
        assertNull(engines.use("g", "claude", LlmSettings(), emptyList()))
        assertNull(engines.use("g", "claude", LlmSettings(), emptyList()))
        assertEquals(1, notes.size)
        assertTrue("Claude" in notes[0] && "key" in notes[0])
    }

    @Test
    fun `one translator per engine, model and key, notes reach the prompt`() {
        keys["gemini"] = "AIza-1"
        val a = engines.use("g", "gemini", LlmSettings(model = "m1", notes = "Vertin: nữ."), listOf("Late." to "Muộn rồi em."))!!
        assertEquals("gemini:m1", a.modelId)
        assertSame(a, engines.use("g", "gemini", LlmSettings(model = "m1", notes = "Vertin: nữ."), emptyList()))
        a.translateCtx(listOf("Hi."), emptyMap())
        val user = made.last().second.users.last()
        assertTrue("Về game:\nVertin: nữ." in user)
        keys["gemini"] = "AIza-2"
        assertNotSame(a, engines.use("g", "gemini", LlmSettings(model = "m1"), emptyList()))
        assertEquals("AIza-2", made.last().first)
    }

    @Test
    fun `a live model gets its own client`() {
        keys["gemini"] = "AIza-1"
        val tr = engines.use("g", "gemini", LlmSettings(model = "pro", liveModel = "lite"), emptyList())!!
        assertEquals(setOf("pro", "lite"), made.map { it.second.model }.toSet())
        tr.live = true
        assertEquals("gemini:lite", tr.modelId)
        made.clear()
        engines.use("g", "gemini", LlmSettings(model = "pro", liveModel = "pro"), emptyList())  // the same: one client
        assertEquals(listOf("pro"), made.map { it.second.model })
    }

    @Test
    fun `suggested models include the default`() {
        for (e in listOf("gemini", "openai", "claude")) assertTrue(DEFAULT_MODELS.getValue(e) in SUGGESTED_MODELS.getValue(e))
    }
}
