package screentrans.text

import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PostprocessFixturesTest {
    private val dir = File(System.getProperty("shared.dir"), "fixtures/postprocess")

    @Test
    fun `fixture set is present`() {
        assertTrue((dir.listFiles { f -> f.extension == "json" }?.size ?: 0) >= 12)
    }

    @TestFactory
    fun fixtures(): List<DynamicTest> = dir.listFiles { f -> f.extension == "json" }!!.sorted().map { file ->
        DynamicTest.dynamicTest(file.nameWithoutExtension) {
            val root = JsonParser.parseString(file.readText()).asJsonObject
            val lines = root["lines"].asJsonArray.map { e ->
                val o = e.asJsonObject
                val b = o["box"].asJsonArray.map { it.asFloat }
                Line(o["text"].asString, b[0], b[1], b[2], b[3], o["angle"]?.asFloat ?: 0f)
            }
            val wantJson = root["expected"].asJsonArray.map { it.asJsonObject }
            val expected = wantJson.map { o -> Triple(o["kind"].asString, o["text"].asString, o["sentences"].asJsonArray.map { it.asString }) }
            val paras = Postprocess.run(lines)
            assertEquals(expected, paras.map { Triple(it.kind.name.lowercase(), it.text, it.sentences) })
            wantJson.zip(paras).forEach { (o, p) -> o["angle"]?.let { assertEquals(it.asFloat, p.angle, 0.01f, "angle") } }
        }
    }

    @Test
    fun `split sentences examples`() {
        val cases = mapOf(
            "Yes. Here we go." to listOf("Yes.", "Here we go."),
            "Wait... what? No!" to listOf("Wait... what?", "No!"),
            "Dr. Who is here. Mrs. Lee too." to listOf("Dr. Who is here.", "Mrs. Lee too."),
            "He said “go.” Then left." to listOf("He said “go.”", "Then left."),
            "Vertin ... was the first to leave." to listOf("Vertin ... was the first to leave."),
            "" to emptyList(),
        )
        for ((text, want) in cases) assertEquals(want, Postprocess.splitSentences(text), text)
    }

    @Test
    fun `empty input`() {
        assertEquals(emptyList(), Postprocess.run(emptyList()))
    }
}
