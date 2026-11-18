package dev.screentrans.core

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import screentrans.text.Glossary
import screentrans.text.Line
import screentrans.text.Paragraph
import screentrans.text.Pipeline
import screentrans.text.Postprocess
import screentrans.text.Segment

const val SUPERSEDED = "superseded"

/** The model bundle has a version file; copy the assets again only when it changed. */
object ModelInstall {
    fun needsCopy(installedVersion: String?, bundledVersion: String): Boolean = installedVersion != bundledVersion
}

/** OCR + the one Pipeline the engine thread owns. */
class EngineBundle<I>(
    val ocr: (I) -> List<Line>,
    val pipeline: Pipeline,
    val warmUp: () -> Unit = {},
    val close: () -> Unit = {},  // releases native resources (ONNX sessions, ML Kit)
)

/**
 * [regions] (region mode only): (l, t, r, b) px rects in [image]. OCR runs once on the image, each
 * line goes to the region containing its centre, and every region is postprocessed on its own.
 *
 * Live: [liveOcr] only OCRs + postprocesses [image] per region ([EngineEvent.OcrDone]);
 * [liveParagraphs] (paragraphs per region, no image) translates sentence by sentence
 * ([EngineEvent.Partial] after each sentence, then [EngineEvent.Done]).
 */
/** Jobs that change the pipeline; never superseded, run before OCR / translation jobs. */
sealed interface EngineControl {
    /** The user's corrections ([fixes]: source to corrected) and glossary terms (target null = keep). */
    data class Correct(val fixes: List<Pair<String, String>>, val terms: List<Pair<String, String?>>) : EngineControl
    /** Another game: its glossary files (JSON text) and the user's translations for it. */
    data class SetGame(val glossaryJson: List<String>, val overrides: Map<String, String>) : EngineControl
}

data class EngineJob<I>(
    val id: Int,
    val fullScreen: Boolean,
    val image: I?,
    val regions: List<IntArray> = emptyList(),
    val liveOcr: Boolean = false,
    val liveParagraphs: List<List<Paragraph>>? = null,
    val control: EngineControl? = null,
)

sealed interface EngineState {
    data object Loading : EngineState
    data object Ready : EngineState
    data class Failed(val message: String) : EngineState
}

sealed interface EngineEvent {
    data class SegmentReady(val jobId: Int, val segment: Segment) : EngineEvent
    data class Done(val jobId: Int, val segments: List<Segment>) : EngineEvent
    data class JobFailed(val jobId: Int, val why: String) : EngineEvent
    data class OcrDone(val jobId: Int, val paragraphs: List<List<Paragraph>>) : EngineEvent
    data class Partial(val jobId: Int, val segments: List<List<Segment>>) : EngineEvent
}

/**
 * Runs OCR + translation on one dispatcher (a single thread in the app), so the Pipeline is never
 * used concurrently. Only the newest waiting job of each kind (user / Live) is kept; older waiting ones fail with
 * [SUPERSEDED]. User jobs run first.
 * Same contract as the Windows TranslationWorker.
 */
class TranslationEngine<I>(
    private val factory: () -> EngineBundle<I>,
    private val scope: CoroutineScope,
    private val dispatcher: CoroutineDispatcher,
) {
    private val _state = MutableStateFlow<EngineState>(EngineState.Loading)
    val state: StateFlow<EngineState> = _state
    private val _events = MutableSharedFlow<EngineEvent>(extraBufferCapacity = 256)
    val events: SharedFlow<EngineEvent> = _events

    private val lock = Any()
    private var pending: EngineJob<I>? = null
    private var liveOcrPending: EngineJob<I>? = null  // Live jobs: one slot per kind, never replace user jobs
    private var liveTranslatePending: EngineJob<I>? = null
    private val controls = ArrayDeque<EngineJob<I>>()  // control jobs: never superseded, run first
    private var bundle: EngineBundle<I>? = null

    fun start() {
        scope.launch(dispatcher) {
            try {
                val b = factory()
                b.warmUp()
                bundle = b
                _state.value = EngineState.Ready
            } catch (e: Throwable) {
                _state.value = EngineState.Failed(e.message ?: e.javaClass.simpleName)
            }
            process()
        }
    }

    /** Thread-safe; call from the UI thread. */
    fun submit(job: EngineJob<I>) {
        val old = synchronized(lock) {
            when {
                job.control != null -> null.also { controls.addLast(job) }
                job.liveParagraphs != null -> liveTranslatePending.also { liveTranslatePending = job }
                job.liveOcr -> liveOcrPending.also { liveOcrPending = job }
                else -> pending.also { pending = job }
            }
        }
        if (old != null) _events.tryEmit(EngineEvent.JobFailed(old.id, SUPERSEDED))
        scope.launch(dispatcher) { process() }
    }

    /**
     * Release the bundle on the engine dispatcher (after any running job). Uses its own scope: the
     * caller usually cancels [scope] right after, which would drop a launch made there.
     */
    fun close() {
        CoroutineScope(dispatcher).launch {
            bundle?.close?.invoke()
            bundle = null
        }
    }

    private fun take(): EngineJob<I>? = synchronized(lock) {
        controls.removeFirstOrNull()
            ?: pending?.also { pending = null }
            ?: liveTranslatePending?.also { liveTranslatePending = null }  // finish shown sentences first
            ?: liveOcrPending.also { liveOcrPending = null }
    }

    private fun process() {
        val s = _state.value
        if (s is EngineState.Failed) {
            while (true) {
                val job = take() ?: return
                _events.tryEmit(EngineEvent.JobFailed(job.id, s.message))
            }
        }
        val b = bundle ?: return
        while (true) {
            val job = take() ?: return
            run(b, job)
        }
    }

    private fun run(b: EngineBundle<I>, job: EngineJob<I>) {
        try {
            when (val c = job.control) {
                is EngineControl.Correct -> {
                    c.fixes.forEach { (src, fixed) -> b.pipeline.correct(src, fixed) }
                    c.terms.forEach { (src, target) -> b.pipeline.addTerm(src, target) }
                    _events.tryEmit(EngineEvent.Done(job.id, emptyList()))
                    return
                }
                is EngineControl.SetGame -> {
                    b.pipeline.setGame(Glossary.load(*c.glossaryJson.toTypedArray()), c.overrides)
                    _events.tryEmit(EngineEvent.Done(job.id, emptyList()))
                    return
                }
                null -> Unit
            }
            val live = job.liveParagraphs
            if (live != null) {
                runLiveTranslate(b, job.id, live)
                return
            }
            val lines = b.ocr(requireNotNull(job.image) { "job without image" })
            fun perRegion() = job.regions.map { r ->
                Postprocess.run(lines.filter { l ->
                    val cx = l.left + l.width / 2
                    val cy = l.top + l.height / 2
                    cx >= r[0] && cx < r[2] && cy >= r[1] && cy < r[3]
                })
            }
            if (job.liveOcr) {
                _events.tryEmit(EngineEvent.OcrDone(job.id, if (job.regions.isEmpty()) listOf(Postprocess.run(lines)) else perRegion()))
                return
            }
            val paragraphs = if (job.fullScreen || job.regions.isEmpty()) Postprocess.run(lines) else perRegion().flatten()
            val segments = if (job.fullScreen) {
                b.pipeline.iterSegments(paragraphs).onEach { _events.tryEmit(EngineEvent.SegmentReady(job.id, it)) }.toList()
            } else {
                b.pipeline.translateParagraphs(paragraphs)
            }
            _events.tryEmit(EngineEvent.Done(job.id, segments))
        } catch (e: Throwable) {
            _events.tryEmit(EngineEvent.JobFailed(job.id, e.message ?: e.javaClass.simpleName))
        }
    }

    private fun runLiveTranslate(b: EngineBundle<I>, jobId: Int, groups: List<List<Paragraph>>) {
        val sizes = groups.map { it.size }
        fun regroup(segs: List<Segment>): List<List<Segment>> {
            var i = 0
            return sizes.map { n -> segs.subList(i, i + n).also { i += n } }
        }
        var last: List<List<Segment>> = groups.map { emptyList() }
        for (segs in b.pipeline.iterSentences(groups.flatten())) {
            last = regroup(segs)
            _events.tryEmit(EngineEvent.Partial(jobId, last))
        }
        _events.tryEmit(EngineEvent.Done(jobId, last.flatten()))
    }
}
