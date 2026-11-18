package dev.screentrans.core.live

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import screentrans.text.Kind
import screentrans.text.Paragraph
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class LiveFixturesTest {
    private val shared = File(System.getProperty("shared.dir"))
    private fun files(dir: String) = File(shared, "fixtures/$dir").listFiles { f -> f.extension == "json" }!!.sorted()

    private fun params(o: JsonObject?) = LiveParams().let { d ->
        if (o == null) d else LiveParams(
            o["interval_ms"]?.asInt ?: d.intervalMs, o["active_interval_ms"]?.asInt ?: d.activeIntervalMs,
            o["settle_ms"]?.asInt ?: d.settleMs, o["max_wait_ms"]?.asInt ?: d.maxWaitMs,
            o["change_threshold"]?.asFloat ?: d.changeThreshold,
        )
    }

    @TestFactory
    fun machine(): List<DynamicTest> = files("live").map { file ->
        DynamicTest.dynamicTest(file.nameWithoutExtension) {
            val root = JsonParser.parseString(file.readText()).asJsonObject
            val m = LiveMachine(params(root["params"]?.asJsonObject))
            val got = mutableListOf<Pair<Int, String>>()
            for (e in root["events"].asJsonArray.map { it.asJsonObject }) {
                val t = e["t"].asInt
                when {
                    e.has("diff") -> if (m.onFrame(t, e["diff"].asFloat) == LiveAction.OCR) got.add(t to "ocr")
                    e.has("ocr_text") -> got.add(t to m.onText(t, e["ocr_text"].asString))
                    e.has("overlay_changed") -> m.onOverlayChanged()
                }
            }
            val want = root["expected"].asJsonArray.map { it.asJsonObject.let { o -> o["t"].asInt to o["action"].asString } }
            assertEquals(want, got)
        }
    }

    @TestFactory
    fun blocks(): List<DynamicTest> = files("live_blocks").map { file ->
        DynamicTest.dynamicTest(file.nameWithoutExtension) {
            val root = JsonParser.parseString(file.readText()).asJsonObject
            val p = root["params"].asJsonObject
            val tracker = BlockTracker(p["max_blocks"].asInt, p["near_px"].asFloat)
            for (step in root["steps"].asJsonArray.map { it.asJsonObject }) {
                val paras = step["paragraphs"].asJsonArray.map { it.asJsonObject }.map { o ->
                    val b = o["box"].asJsonArray.map { it.asFloat }
                    Paragraph(Kind.TEXT, o["text"].asString, listOf(o["text"].asString), b[0], b[1], b[2], b[3])
                }
                val diff = tracker.update(paras)
                val exp = step["expected"].asJsonObject
                fun texts(k: String) = exp[k].asJsonArray.map { it.asString }
                assertEquals(texts("added"), diff.added.map { it.text }, "added")
                assertEquals(texts("kept"), diff.kept.map { it.text }, "kept")
                assertEquals(texts("removed"), diff.removed.map { it.text }, "removed")
            }
        }
    }

    @Test
    fun `next delay and rate limiter`() {
        val m = LiveMachine(LiveParams())
        assertEquals(300, m.nextDelayMs())
        m.onFrame(0, 50f)
        assertEquals(100, m.nextDelayMs())
        val rl = RateLimiter(1000)
        assertTrue(rl.allow(0)); assertFalse(rl.allow(500)); assertTrue(rl.allow(1000))
    }
}
