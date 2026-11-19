package screentrans.text

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import java.io.File
import kotlin.test.assertEquals

/** Same rules as windows/app/translate/llm_prompt.py: shared/fixtures/llm. */
class LlmPromptTest {
    private val dir = File(System.getProperty("shared.dir"), "fixtures/llm")

    private fun json(f: File): JsonObject = JsonParser.parseString(f.readText()).asJsonObject

    @TestFactory
    fun prompts() = dir.listFiles { f -> f.name.startsWith("prompt_") }!!.sorted().map { f ->
        DynamicTest.dynamicTest(f.name) {
            val c = json(f)
            val i = c["input"].asJsonObject
            val context = i["context"].asJsonArray.map { p ->
                val a = p.asJsonArray
                (if (a[0].isJsonNull) null else a[0].asString) to a[1].asString
            }
            val glossary = LinkedHashMap<String, String?>().apply {
                i["glossary"].asJsonObject.entrySet().forEach { (k, v) -> put(k, if (v.isJsonNull) null else v.asString) }
            }
            val examples = i["examples"]?.asJsonArray?.map { it.asJsonArray[0].asString to it.asJsonArray[1].asString }
                ?: emptyList()
            val speaker = i["speaker"]?.takeIf { !it.isJsonNull }?.asString
            val (system, user) = LlmPrompt.buildMessages(i["sentences"].asJsonArray.map { it.asString }, context, speaker,
                glossary, i["notes"]?.asString ?: "", examples)
            val e = c["expected"].asJsonObject
            assertEquals(e["system"].asString, system)
            assertEquals(e["user"].asString, user)
        }
    }

    @TestFactory
    fun replies() = dir.listFiles { f -> f.name.startsWith("reply_") }!!.sorted().map { f ->
        DynamicTest.dynamicTest(f.name) {
            val c = json(f)
            val expected = c["expected"].takeIf { !it.isJsonNull }?.asJsonArray?.map { it.asString }
            assertEquals(expected, LlmPrompt.parseReply(c["text"].asString, c["n"].asInt))
        }
    }

    @Test
    fun `reply schema asks for a list of strings`() {
        val s = JsonParser.parseString(LlmPrompt.REPLY_SCHEMA_JSON).asJsonObject
        assertEquals("array", s["properties"].asJsonObject["translations"].asJsonObject["type"].asString)
        assertEquals(false, s["additionalProperties"].asBoolean)
    }
}
