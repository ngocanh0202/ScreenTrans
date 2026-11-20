package dev.screentrans.core

import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory
import java.io.File
import kotlin.test.assertEquals

/** Live box layout: same cases as windows/tests/test_live_layout.py (shared/fixtures/live_layout). */
class LiveLayoutFixturesTest {
    private val dir = File(System.getProperty("shared.dir"), "fixtures/live_layout")

    private fun greedyLines(words: List<Int>, space: Int): (Int) -> Int = { width ->
        var n = 0
        var cur = -1
        for (w in words) {
            if (cur >= 0 && cur + space + w <= width) cur += space + w else { n++; cur = w }
        }
        n
    }

    @TestFactory
    fun widen(): List<DynamicTest> = JsonParser.parseString(File(dir, "widen.json").readText()).asJsonArray.map { e ->
        val c = e.asJsonObject
        DynamicTest.dynamicTest(c["name"].asString) {
            val lines = greedyLines(c["words"].asJsonArray.map { it.asInt }, c["space"].asInt)
            assertEquals(c["expected"].asInt, Layout.widen(c["width"].asInt, lines, c["room"].asInt, c["px"].asFloat))
        }
    }

    @TestFactory
    fun separate(): List<DynamicTest> = JsonParser.parseString(File(dir, "separate.json").readText()).asJsonArray.map { e ->
        val c = e.asJsonObject
        DynamicTest.dynamicTest(c["name"].asString) {
            val rects = c["rects"].asJsonArray.map { r -> r.asJsonArray.map { it.asFloat }.toFloatArray() }
            val exp = c["expected"].asJsonArray.map { r -> r.asJsonArray.map { it.asFloat } }
            assertEquals(exp, Layout.separate(rects, c["gap"].asFloat).map { it.toList() })
        }
    }
}
