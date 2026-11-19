package dev.screentrans.core

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Test
import screentrans.text.Glossary
import screentrans.text.Kind
import screentrans.text.Line
import screentrans.text.Paragraph
import screentrans.text.Pipeline
import screentrans.text.SentenceTranslator
import screentrans.text.TranslationCache
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class TranslationEngineTest {
    private val lines = listOf(
        Line("Druvis Ill", 37f, 13f, 149f, 29f),
        Line("Hello there.", 26f, 78f, 500f, 31f),
        Line("Far below.", 26f, 300f, 300f, 31f),
    )

    private fun bundle(): EngineBundle<String> {
        val tr = SentenceTranslator { texts -> texts.map { "VI $it" } }
        return EngineBundle(ocr = { _: String -> lines }, pipeline = Pipeline(tr, "fake", Glossary(emptyList()), TranslationCache(100)))
    }

    @Test
    fun `needs copy only when the bundled model version changed`() {
        assertTrue(ModelInstall.needsCopy(null, "1"))
        assertEquals(false, ModelInstall.needsCopy("1", "1"))
        assertTrue(ModelInstall.needsCopy("1", "2"))
    }

    @Test
    fun `ready then region job done`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        testScheduler.advanceUntilIdle()
        assertEquals(EngineState.Ready, engine.state.value)
        engine.submit(EngineJob(1, fullScreen = false, image = "img"))
        testScheduler.advanceUntilIdle()
        val done = events.filterIsInstance<EngineEvent.Done>().single()
        assertEquals(1, done.jobId)
        assertEquals(listOf(Kind.NAME, Kind.TEXT, Kind.TEXT), done.segments.map { it.kind })
        assertEquals("VI Hello there.", done.segments[1].translation)
    }

    @Test
    fun `full screen job emits segments before done`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        engine.submit(EngineJob(7, fullScreen = true, image = "img"))
        testScheduler.advanceUntilIdle()
        val segs = events.filterIsInstance<EngineEvent.SegmentReady>()
        assertEquals(listOf("Druvis III", "Hello there.", "Far below."), segs.map { it.segment.source })
        assertTrue(events.indexOf(segs.last()) < events.indexOfFirst { it is EngineEvent.Done })
    }

    @Test
    fun `waiting jobs are superseded by the newest`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        testScheduler.runCurrent()
        engine.submit(EngineJob(1, false, "a"))
        engine.submit(EngineJob(2, false, "b"))
        engine.submit(EngineJob(3, false, "c"))
        engine.start()  // jobs submitted before the model is ready are kept (newest only)
        testScheduler.advanceUntilIdle()
        assertEquals(listOf(1, 2), events.filterIsInstance<EngineEvent.JobFailed>().filter { it.why == SUPERSEDED }.map { it.jobId })
        assertEquals(listOf(3), events.filterIsInstance<EngineEvent.Done>().map { it.jobId })
    }

    @Test
    fun `factory failure fails the engine and later jobs`() = runTest {
        val engine = TranslationEngine<String>({ error("no model here") }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        testScheduler.advanceUntilIdle()
        val state = engine.state.value
        assertIs<EngineState.Failed>(state)
        assertTrue("no model here" in state.message)
        engine.submit(EngineJob(4, false, "x"))
        testScheduler.advanceUntilIdle()
        val failed = events.filterIsInstance<EngineEvent.JobFailed>().single()
        assertEquals(4, failed.jobId)
        assertTrue("no model here" in failed.why)
    }

    @Test
    fun `close releases the bundle on the engine dispatcher`() = runTest {
        var closed = 0
        val engine = TranslationEngine({
            val b = bundle()
            EngineBundle(b.ocr, b.pipeline, close = { closed++ })
        }, this, StandardTestDispatcher(testScheduler))
        engine.start()
        testScheduler.advanceUntilIdle()
        engine.close()
        testScheduler.advanceUntilIdle()
        assertEquals(1, closed)
    }

    @Test
    fun `region job with several regions postprocesses each region separately in one batch`() = runTest {
        val calls = mutableListOf<List<String>>()
        val ocrLines = listOf(
            Line("Top one.", 10f, 10f, 200f, 30f),
            Line("Bottom one.", 10f, 50f, 200f, 30f),   // close below: would merge into one paragraph
            Line("Outside.", 600f, 600f, 200f, 30f),
        )
        val tr = SentenceTranslator { texts -> calls.add(texts); texts.map { "VI $it" } }
        val engine = TranslationEngine({
            EngineBundle(ocr = { _: String -> ocrLines }, pipeline = Pipeline(tr, "fake", Glossary(emptyList()), TranslationCache(100)))
        }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        engine.submit(EngineJob(5, fullScreen = false, image = "frame",
            regions = listOf(intArrayOf(0, 0, 300, 45), intArrayOf(0, 45, 300, 100))))
        testScheduler.advanceUntilIdle()
        val done = events.filterIsInstance<EngineEvent.Done>().single()
        assertEquals(listOf("Top one.", "Bottom one."), done.segments.map { it.source })
        assertEquals(listOf(listOf("Top one.", "Bottom one.")), calls)
    }

    @Test
    fun `live ocr returns paragraphs per region`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        engine.submit(EngineJob(8, fullScreen = false, image = "img", liveOcr = true,
            regions = listOf(intArrayOf(0, 0, 600, 200), intArrayOf(0, 200, 600, 400))))
        testScheduler.advanceUntilIdle()
        val ocr = events.filterIsInstance<EngineEvent.OcrDone>().single()
        assertEquals(8, ocr.jobId)
        assertEquals(listOf(listOf("Druvis III", "Hello there."), listOf("Far below.")), ocr.paragraphs.map { r -> r.map { it.text } })
        assertTrue(events.none { it is EngineEvent.Done })
    }

    @Test
    fun `live translate emits partials before done`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        val a = Paragraph(Kind.TEXT, "One.", listOf("One."), 0f, 0f, 10f, 10f)
        val b = Paragraph(Kind.TEXT, "Two.", listOf("Two."), 0f, 20f, 10f, 30f)
        engine.submit(EngineJob<String>(9, fullScreen = false, image = null, liveParagraphs = listOf(listOf(a), listOf(b))))
        testScheduler.advanceUntilIdle()
        val partials = events.filterIsInstance<EngineEvent.Partial>()
        assertEquals(2, partials.size)
        assertEquals(listOf(listOf("VI One."), listOf("VI Two.")), partials.last().segments.map { r -> r.map { it.translation } })
        assertTrue(events.indexOf(partials.last()) < events.indexOfFirst { it is EngineEvent.Done })
    }

    @Test
    fun `live jobs never supersede user jobs`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        testScheduler.runCurrent()
        engine.submit(EngineJob(1, false, "a"))
        engine.submit(EngineJob(2, false, "b", liveOcr = true))
        engine.submit(EngineJob(3, false, "c", liveOcr = true))
        engine.start()
        testScheduler.advanceUntilIdle()
        assertEquals(listOf(2), events.filterIsInstance<EngineEvent.JobFailed>().map { it.jobId })
        assertEquals(listOf(1), events.filterIsInstance<EngineEvent.Done>().map { it.jobId })
        assertEquals(listOf(3), events.filterIsInstance<EngineEvent.OcrDone>().map { it.jobId })
    }

    @Test
    fun `correct and set game control jobs are never superseded and apply to later jobs`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        testScheduler.runCurrent()
        engine.submit(EngineJob(1, false, null as String?, control = EngineControl.Correct(listOf("Hello there." to "Chào cậu."), emptyList())))
        engine.submit(EngineJob(2, false, "img"))
        engine.start()
        testScheduler.advanceUntilIdle()
        assertTrue(events.none { it is EngineEvent.JobFailed })
        val done = events.filterIsInstance<EngineEvent.Done>().single { it.jobId == 2 }
        assertEquals("Chào cậu.", done.segments[1].translation)
        engine.submit(EngineJob(3, false, null as String?, control = EngineControl.SetGame(listOf("""{"entries": []}"""), mapOf("Far below." to "Tít dưới."))))
        engine.submit(EngineJob(4, false, "img"))
        testScheduler.advanceUntilIdle()
        val after = events.filterIsInstance<EngineEvent.Done>().single { it.jobId == 4 }
        assertEquals(listOf("VI Hello there.", "Tít dưới."), after.segments.drop(1).map { it.translation })
    }

    @Test
    fun `live translate does not supersede a waiting live ocr`() = runTest {
        val engine = TranslationEngine({ bundle() }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        testScheduler.runCurrent()
        engine.submit(EngineJob(1, false, "img", liveOcr = true))
        engine.submit(EngineJob<String>(2, false, null, liveParagraphs = listOf(emptyList())))
        engine.start()
        testScheduler.advanceUntilIdle()
        assertTrue(events.none { it is EngineEvent.JobFailed })
        assertEquals(listOf(1), events.filterIsInstance<EngineEvent.OcrDone>().map { it.jobId })
    }

    @Test
    fun `i1 a tilted line far from the origin goes to the region it is drawn in`() = runTest {
        // a 15 degree line drawn centred at screen (800, 1300); its box is in the tilted frame
        val (dcx, dcy) = screentrans.text.Deskew.rotate(800f, 1300f, 15f)
        val tilted = listOf(Line("A tilted line of the quest.", dcx - 150f, dcy - 15f, 300f, 30f, 15f))
        val tr = SentenceTranslator { texts -> texts.map { "VI $it" } }
        val engine = TranslationEngine({
            EngineBundle(ocr = { _: String -> tilted }, pipeline = Pipeline(tr, "fake", Glossary(emptyList()), TranslationCache(100)))
        }, this, StandardTestDispatcher(testScheduler))
        val events = mutableListOf<EngineEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { engine.events.collect { events.add(it) } }
        engine.start()
        engine.submit(EngineJob(30, fullScreen = false, image = "frame", liveOcr = true, regions = listOf(intArrayOf(200, 1000, 900, 1600))))
        testScheduler.advanceUntilIdle()
        assertEquals(listOf("A tilted line of the quest."), events.filterIsInstance<EngineEvent.OcrDone>().single().paragraphs[0].map { it.text })
    }
}
