package dev.screentrans.core.live

import org.junit.jupiter.api.Test
import screentrans.text.Kind
import screentrans.text.Paragraph
import screentrans.text.Postprocess
import screentrans.text.Segment
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Same cases as windows/tests/test_live_controller.py (4b), without capture (diffs are given directly). */
class LiveSessionTest {
    private class Host : LiveHost {
        var ids = 0
        val ocr = mutableListOf<Pair<Int, Boolean>>()
        val translate = mutableListOf<Pair<Int, List<List<Paragraph>>>>()
        val blocks = LinkedHashMap<String, String>()
        val lineHeights = LinkedHashMap<String, Float>()
        override fun requestOcr(final: Boolean): Int = (++ids).also { ocr.add(it to final) }
        override fun requestTranslate(paragraphs: List<List<Paragraph>>): Int = (++ids).also { translate.add(it to paragraphs) }
        val angles = LinkedHashMap<String, Float>()
        var draws = 0
        override fun setBlock(region: Int, key: String, text: String, box: FloatArray, kind: Kind, lineHeight: Float, angle: Float) {
            draws++
            blocks["$region:$key"] = text
            lineHeights["$region:$key"] = lineHeight
            angles["$region:$key"] = angle
        }
        override fun removeBlock(region: Int, key: String) {
            blocks.remove("$region:$key")
        }
    }

    private val params = LiveParams(partialIntervalMs = 500)
    private fun para(text: String, top: Float = 0f) =
        Paragraph(Kind.TEXT, text, Postprocess.splitSentences(text), 0f, top, 300f, top + 20f)

    private fun session(h: Host, scope: String = "region", regions: Int = 1) = LiveSession(params, scope, regions, host = h)

    private fun drive(s: LiveSession, from: Int, until: Int, diff: (Int) -> Float) {
        var t = from
        while (t <= until) { s.onFrame(t, diff(t)); t += 100 }
    }

    private fun sources(job: Pair<Int, List<List<Paragraph>>>) = job.second.flatten().map { it.text }

    private fun translate(s: LiveSession, job: Pair<Int, List<List<Paragraph>>>) {
        val segs = job.second.map { g -> g.map { Segment(Kind.TEXT, it.text, "VI ${it.text}", it.left, it.top, it.right, it.bottom) } }
        s.onPartial(job.first, segs)
        s.onJobEnded(job.first)
    }

    @Test
    fun `still screen ocrs once at start then never`() {
        val h = Host()
        drive(session(h), 0, 3000) { 0f }
        assertEquals(listOf(1 to true), h.ocr)
    }

    @Test
    fun `sentences appear while the text is typing`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(emptyList()))
        drive(s, 100, 600) { t -> if (t <= 1500 && t % 200 == 100) 255f else if (t <= 1500) 255f else 0f }
        val partial = h.ocr.last()
        assertEquals(false, partial.second)
        s.onOcrDone(partial.first, listOf(listOf(para("Where are you going? The"))))
        assertEquals(listOf("Where are you going?"), sources(h.translate.last()))
        translate(s, h.translate.last())
        assertEquals(listOf("VI Where are you going?"), h.blocks.values.toList())
        drive(s, 700, 2500) { t -> if (t <= 1500) 255f else 0f }
        val final = h.ocr.last()
        assertEquals(true, final.second)
        s.onOcrDone(final.first, listOf(listOf(para("Where are you going? The station is closed today."))))
        assertEquals(listOf("The station is closed today."), sources(h.translate.last()))
        translate(s, h.translate.last())
        assertEquals(listOf("VI Where are you going? VI The station is closed today."), h.blocks.values.toList())
    }

    @Test
    fun `unchanged block is not translated again and gone block is removed`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello."))))
        translate(s, h.translate.last())
        s.debugExpectOcr(99, final = true)
        s.onOcrDone(99, listOf(listOf(para("Hello."))))
        assertEquals(1, h.translate.size)
        s.debugExpectOcr(100, final = true)
        s.onOcrDone(100, listOf(emptyList()))
        assertTrue(h.blocks.isEmpty())
    }

    @Test
    fun `superseded translation is requested again`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello."))))
        val lost = h.translate.last().first
        s.onJobFailed(lost)
        s.debugExpectOcr(99, final = true)
        s.onOcrDone(99, listOf(listOf(para("Hello."))))
        assertEquals(2, h.translate.size)
        assertEquals(listOf("Hello."), sources(h.translate.last()))
    }

    @Test
    fun `screen scope rate limits ocr`() {
        val h = Host()
        drive(session(h, scope = "screen"), 0, 4000) { 255f }
        assertTrue(h.ocr.size in 1..5, "ocr ${h.ocr.size}")
    }

    @Test
    fun `stop ignores late results`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hi."))))
        val job = h.translate.last()
        s.stop()
        translate(s, job)
        assertTrue(h.blocks.isEmpty())
    }

    @Test
    fun `name line is shown untranslated`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(Paragraph(Kind.NAME, "Druvis III", emptyList(), 0f, 0f, 100f, 20f), para("Hello.", 30f))))
        assertEquals(listOf("Hello."), sources(h.translate.last()))
        assertTrue("Druvis III" in h.blocks.values)
    }

    @Test
    fun `own redraw is ignored only when overlays are captured`() {
        val h = Host()
        val s = session(h)
        s.overlaysInCapture = true
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hi."))))
        translate(s, h.translate.last())
        s.onFrame(100, 255f)  // the frame showing our own block
        assertEquals(false, s.machine.changing)
        val h2 = Host()
        val s2 = session(h2)  // single-app capture: our overlay is not in the frames
        s2.onFrame(0, 0f)
        s2.onOcrDone(h2.ocr.last().first, listOf(listOf(para("Hi."))))
        translate(s2, h2.translate.last())
        s2.onFrame(100, 255f)
        assertEquals(true, s2.machine.changing)
    }

    @Test
    fun `shown segments and apply correction`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello. Bye."))))
        translate(s, h.translate.last())
        assertEquals(listOf("Hello." to "VI Hello.", "Bye." to "VI Bye."), s.shownSegments().map { it.source to it.translation })
        s.applyCorrection("Hello.", "Chào.")
        assertEquals(listOf("Chào. VI Bye."), h.blocks.values.toList())
    }

    @Test
    fun `c1 typing that stops just before max wait still gets a final read`() {
        val h = Host()
        val s = session(h)
        var t = 0
        while (t < 4000) {
            s.onFrame(t, if (t < 2000) 255f else 0f)
            if (s.ocrJob != -1) s.onOcrDone(s.ocrJob, listOf(emptyList()))
            t += 100
        }
        assertTrue(h.ocr.drop(1).any { it.second }, "ocr ${h.ocr}")
    }

    @Test
    fun `c1 a lost final ocr is requested again`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onJobFailed(h.ocr.last().first)
        s.onFrame(300, 0f)
        assertEquals(2, h.ocr.size)
    }

    @Test
    fun `c2 a block read twice the same is finished even while the screen animates`() {
        val h = Host()
        val s = session(h, scope = "screen")
        val line = para("Press the button to continue")
        s.debugExpectOcr(90, final = false)
        s.onOcrDone(90, listOf(listOf(line)), nowMs = 0)
        assertTrue(h.translate.isEmpty())
        s.debugExpectOcr(91, final = false)
        s.onOcrDone(91, listOf(listOf(line)), nowMs = 1000)  // same text, but maybe still fading in
        assertTrue(h.translate.isEmpty())
        s.debugExpectOcr(92, final = false)
        s.onOcrDone(92, listOf(listOf(line)), nowMs = 1600)  // unchanged for 1.6 s: it has stopped
        assertEquals(listOf("Press the button to continue"), sources(h.translate.last()))
    }

    @Test
    fun `i6 misread last glyph keeps the translation and moved blocks carry theirs`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Where are you going? The sta"))))
        translate(s, h.translate.last())
        s.debugExpectOcr(99, final = false)
        s.onOcrDone(99, listOf(listOf(para("Where are you going? The sla"))))
        assertEquals(listOf("VI Where are you going?"), h.blocks.values.toList())
        val n = h.translate.size
        s.debugExpectOcr(100, final = true)
        s.onOcrDone(100, listOf(listOf(para("Where are you going?", 200f))))
        assertEquals(n, h.translate.size)
        assertEquals(listOf("VI Where are you going?"), h.blocks.values.toList())
    }

    @Test
    fun `blocks carry the source line height`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hi.").copy(lineHeight = 30f))))
        translate(s, h.translate.last())
        assertEquals(30f, h.lineHeights.values.single())
    }

    @Test
    fun `ocr noise and ui labels are not translated`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        val noise = Paragraph(Kind.TEXT, "St3loo 3,", listOf("St3loo 3,"), 0f, 0f, 200f, 40f, 40f)
        val label = Paragraph(Kind.TEXT, "AUTO", listOf("AUTO"), 300f, 0f, 390f, 40f, 40f)
        val line = Paragraph(Kind.TEXT, "Where are you going?", listOf("Where are you going?"), 0f, 100f, 380f, 140f, 40f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(noise, label, line)))
        assertEquals(listOf("Where are you going?"), sources(h.translate.last()))
    }

    @Test
    fun `a superseded translation is requested again at once even if the screen stays still`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello."))))
        val lost = h.translate.last().first
        s.onJobFailed(lost, superseded = true)
        assertEquals(2, h.translate.size)
        assertEquals(listOf("Hello."), sources(h.translate.last()))
        translate(s, h.translate.last())
        assertEquals(listOf("VI Hello."), h.blocks.values.toList())
        val n = h.translate.size
        s.debugExpectOcr(50, final = true)
        s.onOcrDone(50, listOf(listOf(para("Bye."))))
        s.onJobFailed(h.translate.last().first, superseded = false)  // a real error: wait for the next OCR
        assertEquals(n + 1, h.translate.size)
    }

    @Test
    fun `tilted blocks keep their angle`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello there friend.").copy(angle = -10f))))
        translate(s, h.translate.last())
        assertEquals(-10f, h.angles.values.single())
    }

    @Test
    fun `m7 a late translation does not overwrite the users fix`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello."))))
        val late = h.translate.last()
        s.applyCorrection("Hello.", "Chào cậu.")
        translate(s, late)
        assertEquals(listOf("Chào cậu."), h.blocks.values.toList())
    }

    @Test
    fun `m8 a kept block that moved is redrawn at its new place`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello."))))
        translate(s, h.translate.last())
        val before = h.draws
        s.debugExpectOcr(99, final = true)
        s.onOcrDone(99, listOf(listOf(Paragraph(Kind.TEXT, "Hello.", listOf("Hello."), 8f, 6f, 308f, 26f))))
        assertEquals(before + 1, h.draws)
    }

    /** The screen changes at [t], settles, and the final OCR reads [paras]. */
    private fun read(s: LiveSession, h: Host, t: Int, vararg paras: Paragraph) {
        val before = h.ocr.size
        drive(s, t, t + 1000) { tt -> if (tt == t) 255f else 0f }
        assertTrue(h.ocr.size > before, "no OCR after the change at $t")
        s.onOcrDone(h.ocr.last().first, listOf(paras.toList()))
    }

    @Test
    fun `a sentence translated before is shown at once without a new request`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello there."))))
        translate(s, h.translate.last())
        read(s, h, 100, para("Something else."))
        translate(s, h.translate.last())
        val n = h.translate.size
        read(s, h, 2000, para("Hello there."))  // the first line again (a new block)
        assertEquals(n, h.translate.size)
        assertEquals(listOf("VI Hello there."), h.blocks.values.toList())
    }

    @Test
    fun `remembered translations follow the users fix`() {
        val h = Host()
        val s = session(h)
        s.onFrame(0, 0f)
        s.onOcrDone(h.ocr.last().first, listOf(listOf(para("Hello there."))))
        translate(s, h.translate.last())
        s.applyCorrection("Hello there.", "Chào bạn.")
        read(s, h, 100)
        read(s, h, 2000, para("Hello there."))
        assertEquals(listOf("Chào bạn."), h.blocks.values.toList())
    }
}
