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
}
