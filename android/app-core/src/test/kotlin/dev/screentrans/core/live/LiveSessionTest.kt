package dev.screentrans.core.live

import org.junit.jupiter.api.Test
import screentrans.text.Kind
import screentrans.text.Paragraph
import screentrans.text.Segment
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Same cases as windows/tests/test_live_controller.py, without capture (diffs are given directly). */
class LiveSessionTest {
    private class Host : LiveHost {
        var ids = 0
        val ocr = mutableListOf<Int>()
        val translate = mutableListOf<Pair<Int, List<List<Paragraph>>>>()
        var shown: List<List<Segment>>? = null
        val blocks = LinkedHashMap<String, Segment>()
        override fun requestOcr(): Int = (++ids).also { ocr.add(it) }
        override fun requestTranslate(paragraphs: List<List<Paragraph>>): Int = (++ids).also { translate.add(it to paragraphs) }
        override fun showDialogue(segments: List<List<Segment>>) { shown = segments }
        override fun setBlock(key: String, segment: Segment) { blocks[key] = segment }
        override fun removeBlock(key: String) { blocks.remove(key) }
    }

    private fun para(text: String, top: Float = 0f) = Paragraph(Kind.TEXT, text, listOf(text), 0f, top, 100f, top + 20f)
    private fun seg(src: String, vi: String) = Segment(Kind.TEXT, src, vi, 0f, 0f, 100f, 20f)

    private fun drive(s: LiveSession, diffs: (Int) -> Float, untilMs: Int, step: Int = 100) {
        var t = 0
        while (t <= untilMs) { s.onFrame(t, diffs(t)); t += step }
    }

    @Test
    fun `typing then still gives one ocr`() {
        val h = Host()
        val s = LiveSession(LiveParams(), area = false, host = h)
        drive(s, { t -> if (t in 100..400) 255f else 0f }, 1500)
        assertEquals(1, h.ocr.size)
    }

    @Test
    fun `still screen never ocrs`() {
        val h = Host()
        drive(LiveSession(LiveParams(), area = false, host = h), { 0f }, 3000)
        assertEquals(0, h.ocr.size)
    }

    @Test
    fun `ocr text is translated progressively and only once`() {
        val h = Host()
        val s = LiveSession(LiveParams(), area = false, host = h)
        drive(s, { t -> if (t == 100) 255f else 0f }, 800)
        s.onOcrDone(h.ocr.last(), listOf(listOf(para("Hello there."))), 900)
        val (trId, paras) = h.translate.single()
        assertEquals("Hello there.", paras[0][0].text)
        s.onPartial(trId, listOf(listOf(seg("Hello there.", "Xin chào."))))
        assertEquals("Xin chào.", h.shown!![0][0].translation)
        drive(s, { t -> if (t == 100) 255f else 0f }, 800)
        s.onOcrDone(h.ocr.last(), listOf(listOf(para("Hello there."))), 1000)
        assertEquals(1, h.translate.size)
    }

    @Test
    fun `stop ignores late results`() {
        val h = Host()
        val s = LiveSession(LiveParams(), area = false, host = h)
        drive(s, { t -> if (t == 100) 255f else 0f }, 800)
        s.onOcrDone(h.ocr.last(), listOf(listOf(para("Hi."))), 900)
        val trId = h.translate.single().first
        s.stop()
        s.onPartial(trId, listOf(listOf(seg("Hi.", "Chào."))))
        assertEquals(null, h.shown)
    }

    @Test
    fun `stale ocr result is ignored`() {
        val h = Host()
        val s = LiveSession(LiveParams(), area = false, host = h)
        drive(s, { t -> if (t == 100) 255f else 0f }, 800)
        s.onOcrDone(12345, listOf(listOf(para("Hi."))), 900)
        assertEquals(0, h.translate.size)
    }

    @Test
    fun `area mode rate limits and translates only new blocks`() {
        val h = Host()
        val s = LiveSession(LiveParams(), area = true, host = h)
        drive(s, { 255f }, 4000)
        assertTrue(h.ocr.size in 1..3, "ocr ${h.ocr.size}")
        val a = para("Bubble one.")
        s.onOcrDone(h.ocr.first(), listOf(listOf(a)), 4100)
        val (trId, paras) = h.translate.single()
        assertEquals(listOf(listOf(a)), paras)
        s.onPartial(trId, listOf(listOf(seg("Bubble one.", "Bong bóng một."))))
        assertEquals(listOf("Bong bóng một."), h.blocks.values.map { it.translation })
        s.debugSetOcrJob(500)
        s.onOcrDone(500, listOf(listOf(a)), 5200)
        assertEquals(1, h.translate.size)
        s.debugSetOcrJob(501)
        s.onOcrDone(501, listOf(emptyList()), 6300)  // bubble gone
        assertTrue(h.blocks.isEmpty())
    }
}
