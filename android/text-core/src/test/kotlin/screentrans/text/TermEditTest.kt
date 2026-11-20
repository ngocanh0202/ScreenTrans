package screentrans.text

import com.google.gson.JsonArray
import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import java.io.File
import kotlin.test.assertEquals

/** Same rules as windows/app/text/term_edit.py: shared/fixtures/term_edit. */
class TermEditTest {
    private val dir = File(System.getProperty("shared.dir"), "fixtures/term_edit")

    private fun rows(a: JsonArray): List<TermEdit.Row> = a.map { r ->
        val x = r.asJsonArray
        TermEdit.Row(x[0].asString, if (x[1].isJsonNull) null else x[1].asString, x[2].asBoolean)
    }

    private fun cases(name: String) = JsonParser.parseString(File(dir, name).readText()).asJsonArray.map { it.asJsonObject }

    @TestFactory
    fun parse(): List<DynamicTest> = cases("parse.json").map { c ->
        DynamicTest.dynamicTest(c["name"].asString) {
            val exp = if (c["rows"].isJsonNull) null else rows(c["rows"].asJsonArray)
            assertEquals(exp, TermEdit.parse(c["text"].asString))
        }
    }

    @TestFactory
    fun clean(): List<DynamicTest> = cases("clean.json").map { c ->
        DynamicTest.dynamicTest(c["name"].asString) {
            assertEquals(rows(c["expected"].asJsonArray), TermEdit.clean(rows(c["rows"].asJsonArray)))
        }
    }

    @Test
    fun `dump reads back in the glossary format`() {
        val r = listOf(TermEdit.Row("Vertin", null, true), TermEdit.Row("storm", "Bão", false))
        val text = TermEdit.dump(r)
        assertEquals(r, TermEdit.parse(text))
        val e = JsonParser.parseString(text).asJsonObject["entries"].asJsonArray
        assertEquals("keep", e[0].asJsonObject["type"].asString)
        assertEquals(false, e[0].asJsonObject.has("target"))
        assertEquals("map", e[1].asJsonObject["type"].asString)
        // and the app's glossary loader reads it
        Glossary.load(text)
    }
}
