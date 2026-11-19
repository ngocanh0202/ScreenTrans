package dev.screentrans.core.live

import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory
import screentrans.text.Kind
import screentrans.text.Paragraph
import java.io.File
import kotlin.test.assertEquals

class LiveFilterTest {
    private val file = File(System.getProperty("shared.dir"), "fixtures/live_filter/cases.json")

    @TestFactory
    fun cases(): List<DynamicTest> = JsonParser.parseString(file.readText()).asJsonObject["cases"].asJsonArray.map { e ->
        val c = e.asJsonObject
        DynamicTest.dynamicTest(c["text"].asString) {
            val b = c["box"].asJsonArray.map { it.asFloat }
            val kind = if (c["kind"].asString == "name") Kind.NAME else Kind.TEXT
            val p = Paragraph(kind, c["text"].asString, listOf(c["text"].asString), b[0], b[1], b[2], b[3], c["line_height"].asFloat)
            assertEquals(c["keep"].asBoolean, LiveFilter.worthTranslating(p), c["why"].asString)
        }
    }
}
