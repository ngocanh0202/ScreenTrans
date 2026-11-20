package dev.screentrans.core.live

import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import screentrans.text.Line
import screentrans.text.Postprocess
import java.io.File
import kotlin.math.abs
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BlockStyleTest {
    private val dir = File(System.getProperty("shared.dir"), "fixtures/live_style")

    @TestFactory
    fun fixtures(): List<DynamicTest> = dir.listFiles { f -> f.extension == "json" }!!.sorted().map { file ->
        DynamicTest.dynamicTest(file.nameWithoutExtension) {
            val root = JsonParser.parseString(file.readText()).asJsonObject
            val w = root["width"].asInt
            val h = root["height"].asInt
            val px = root["pixels"].asJsonArray.flatMap { row -> row.asJsonArray.map { (0xFF000000.toInt() or it.asString.toInt(16)) } }.toIntArray()
            val got = BlockStyle.sample(px, w, h)
            val exp = root["expected"]
            if (exp.isJsonNull) assertNull(got)
            else {
                assertNotNull(got)
                val t = exp.asJsonObject["text"].asJsonArray.map { it.asInt }
                val b = exp.asJsonObject["bg"].asJsonArray.map { it.asInt }
                assertTrue(listOf(got.textR, got.textG, got.textB).zip(t).all { (a, e) -> abs(a - e) <= 8 }, "text $got")
                assertTrue(listOf(got.bgR, got.bgG, got.bgB).zip(b).all { (a, e) -> abs(a - e) <= 8 }, "bg $got")
            }
        }
    }

    @Test
    fun `font size follows the source line height`() {
        assertEquals(24f, BlockStyle.fontPxFor(30f))
        assertNull(BlockStyle.fontPxFor(0f))
    }

    @Test
    fun `paragraph keeps the median line height`() {
        val p = Postprocess.run(listOf(Line("Where are you going? The", 20f, 100f, 400f, 30f), Line("station is closed today.", 20f, 134f, 380f, 32f))).single()
        assertEquals(31f, p.lineHeight)
    }

    @Test
    fun `style cells match the shared fixtures`() {
        val file = File(System.getProperty("shared.dir"), "fixtures/live_style_cells/cells.json")
        for (e in JsonParser.parseString(file.readText()).asJsonArray) {
            val c = e.asJsonObject
            val box = c["box"].asJsonArray.map { it.asFloat }
            val size = c["size"].asJsonArray.map { it.asInt }
            assertEquals(c["cell"].asString, BlockStyle.styleCell(box[0], box[1], size[0], size[1], c["kind"].asString), c["name"].asString)
        }
    }
}
