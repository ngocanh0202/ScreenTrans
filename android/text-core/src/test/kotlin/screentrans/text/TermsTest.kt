package screentrans.text

import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory
import java.io.File
import kotlin.test.assertEquals

/** Same rules as windows/app/text/terms.py: shared/fixtures/terms. */
class TermsTest {
    private val shared = File(System.getProperty("shared.dir"))
    private val dir = File(shared, "fixtures/terms")
    private val common = File(shared, "glossary/common_words_en.txt").readLines().map { it.trim().lowercase() }.toSet()

    @TestFactory
    fun spans() = JsonParser.parseString(File(dir, "span.json").readText()).asJsonArray.map { e ->
        val c = e.asJsonObject
        DynamicTest.dynamicTest(c["expected"].asString) {
            assertEquals(c["expected"].asString, Terms.span(Terms.tokens(c["sentence"].asString), c["from"].asInt, c["to"].asInt))
        }
    }

    @TestFactory
    fun suggestions() = JsonParser.parseString(File(dir, "suggest.json").readText()).asJsonArray.map { e ->
        val c = e.asJsonObject
        DynamicTest.dynamicTest(c["name"].asString) {
            val got = Terms.suggestNames(c["sentences"].asJsonArray.map { it.asString }, common,
                c["known"].asJsonArray.map { it.asString }.toSet())
            assertEquals(c["expected"].asJsonArray.map { it.asString }, got)
        }
    }
}
