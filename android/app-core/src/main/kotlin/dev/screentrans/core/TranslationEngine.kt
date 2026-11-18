package dev.screentrans.core

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import screentrans.text.Line
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
 */
data class EngineJob<I>(val id: Int, val fullScreen: Boolean, val image: I, val regions: List<IntArray> = emptyList())

sealed interface EngineState {
    data object Loading : EngineState
    data object Ready : EngineState
    data class Failed(val message: String) : EngineState
}

sealed interface EngineEvent {
    data class SegmentReady(val jobId: Int, val segment: Segment) : EngineEvent
    data class Done(val jobId: Int, val segments: List<Segment>) : EngineEvent
    data class JobFailed(val jobId: Int, val why: String) : EngineEvent
}

/**
 * Runs OCR + translation on one dispatcher (a single thread in the app), so the Pipeline is never
 * used concurrently. Only the newest waiting job is kept; older waiting ones fail with [SUPERSEDED].
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
        val old = synchronized(lock) { pending.also { pending = job } }
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

    private fun take(): EngineJob<I>? = synchronized(lock) { pending.also { pending = null } }

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
            val lines = b.ocr(job.image)
            val paragraphs = if (job.fullScreen || job.regions.isEmpty()) Postprocess.run(lines)
            else job.regions.flatMap { r ->
                Postprocess.run(lines.filter { l ->
                    val cx = l.left + l.width / 2
                    val cy = l.top + l.height / 2
                    cx >= r[0] && cx < r[2] && cy >= r[1] && cy < r[3]
                })
            }
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
}
