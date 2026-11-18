package dev.screentrans.core.profile

import com.google.gson.JsonParser
import dev.screentrans.core.live.Thumb
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import java.io.File
import kotlin.test.assertEquals

class ProfileFixturesTest {
    private val dir = File(System.getProperty("shared.dir"), "fixtures/profiles")

    @TestFactory
    fun fixtures(): List<DynamicTest> = dir.listFiles { f -> f.extension == "json" }!!.sorted().map { file ->
        DynamicTest.dynamicTest(file.nameWithoutExtension) {
            val root = JsonParser.parseString(file.readText()).asJsonObject
            val input = root["input"]
            val text = if (input.isJsonPrimitive) input.asString else input.toString()
            val expected = root["expected"]
            val got = Profile.parse(text)
            if (expected.isJsonNull) assertEquals(null, got)
            else assertEquals(expected, JsonParser.parseString(got!!.serialize()))
        }
    }

    @Test
    fun `round trip`() {
        val p = Profile("a", "A", scope = "screen", regions = listOf(listOf(0.1, 0.2, 0.3, 0.4)), overrides = mapOf("Hi." to "Chào."))
        assertEquals(p, Profile.parse(p.serialize()))
    }

    @Test
    fun `mask leaves ignored pixels out of the diff`() {
        val a = FloatArray(4) { 0f }
        val b = floatArrayOf(255f, 255f, 0f, 0f)
        assertEquals(0f, Thumb.diff(a, b, booleanArrayOf(false, false, true, true)))
        assertEquals(255f, Thumb.diff(a, b, booleanArrayOf(true, true, false, false)))
        assertEquals(0f, Thumb.diff(a, b, BooleanArray(4)))
        assertEquals(127.5f, Thumb.diff(a, b))
    }
}
