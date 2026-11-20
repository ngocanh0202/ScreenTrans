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
    val llm: dev.screentrans.core.llm.LlmEngines? = null,  // remote LLM engines per game (Phase 5)
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
    /** Another game: its glossary files (JSON text), the user's translations, its translation engine. */
    data class SetGame(
        val glossaryJson: List<String>,
        val overrides: Map<String, String>,
        val game: String? = null,
        val engine: String = "local",
        val llm: dev.screentrans.core.llm.LlmSettings = dev.screentrans.core.llm.LlmSettings(),
    ) : EngineControl
}

data class EngineJob<I>(
    val id: Int,
    val fullScreen: Boolean,
    val image: I?,
    val regions: List<IntArray> = emptyList(),
    val liveOcr: Boolean = false,
    val liveParagraphs: List<List<Paragraph>>? = null,
    val liveSpeaker: String? = null,  // the dialogue box's name line, for a remote LLM
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
    /** Something the user should know (a remote engine fell back to the on-device model). */
    data class Notice(val message: String) : EngineEvent
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
    /** Live OCR runs here: a slow (remote) translation on [dispatcher] never stops Live from reading the screen. */
    private val ocrDispatcher: CoroutineDispatcher = dispatcher,
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
    @Volatile
    private var bundle: EngineBundle<I>? = null

    fun start() {
        scope.launch(dispatcher) {
            try {
                val b = factory()
                b.llm?.notify = { _events.tryEmit(EngineEvent.Notice(it)) }
                b.warmUp()
                activeModelId = b.pipeline.activeModelId
                bundle = b
                _state.value = EngineState.Ready
            } catch (e: Throwable) {
                _state.value = EngineState.Failed(e.message ?: e.javaClass.simpleName)
            }
            process()
            scope.launch(ocrDispatcher) { processOcr() }
        }
    }

    /**
     * Load the model again (another one was chosen in Settings → Model): built on the engine dispatcher, swapped
     * in, the old bundle closed on the OCR dispatcher once its running Live OCR is over. When the new model fails,
     * the old one keeps translating and the user is told. The caller sends the game again (SetGame).
     */
    fun reload() {
        scope.launch(dispatcher) {
            val old = bundle  // null: the first load failed, this is a new try
            val b = try {
                factory().also { it.llm?.notify = { m -> _events.tryEmit(EngineEvent.Notice(m)) }; it.warmUp() }
            } catch (e: Throwable) {
                _events.tryEmit(EngineEvent.Notice("Không nạp được model: ${e.message ?: e.javaClass.simpleName}"))
                return@launch
            }
            bundle = b
            remote = null  // the old bundle's remote engines: SetGame makes new ones
            activeModelId = b.pipeline.activeModelId
            _state.value = EngineState.Ready
            if (old != null) CoroutineScope(ocrDispatcher).launch {
                old.llm?.close()
                old.close()
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
        if (job.liveOcr && job.control == null && job.liveParagraphs == null) scope.launch(ocrDispatcher) { processOcr() }
        else scope.launch(dispatcher) { process() }
    }

    /**
     * Release the bundle on the engine dispatcher (after any running job). Uses its own scope: the
     * caller usually cancels [scope] right after, which would drop a launch made there.
     */
    fun close() {
        CoroutineScope(dispatcher).launch {
            bundle?.llm?.close()
            bundle?.close?.invoke()
            bundle = null
        }
    }

    private fun take(): EngineJob<I>? = synchronized(lock) {
        controls.removeFirstOrNull()
            ?: pending?.also { pending = null }
            ?: liveTranslatePending.also { liveTranslatePending = null }
    }

    private fun takeOcr(): EngineJob<I>? = synchronized(lock) { liveOcrPending.also { liveOcrPending = null } }

    /** Live OCR on [ocrDispatcher]: only OCR + postprocess (no Pipeline state), so it may run beside a translation. */
    private fun processOcr() {
        val s = _state.value
        if (s is EngineState.Failed) {
            while (true) {
                val job = takeOcr() ?: return
                _events.tryEmit(EngineEvent.JobFailed(job.id, s.message))
            }
        }
        val b = bundle ?: return
        while (true) {
            val job = takeOcr() ?: return
            run(b, job)
        }
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

    private var remote: dev.screentrans.core.llm.LlmTranslator? = null

    /** The model translating now (corrections.jsonl credits it), updated on each SetGame. */
    @Volatile
    var activeModelId: String = ""
        private set

    private fun run(b: EngineBundle<I>, job: EngineJob<I>) {
        if (!job.liveOcr) {
            remote?.timeoutMs = if (job.liveParagraphs != null) 2500 else 6000  // Live must not stall
            remote?.live = job.liveParagraphs != null  // Live may use its own (faster) model
        }
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
                    remote = try {
                        b.llm?.use(c.game, c.engine, c.llm, b.pipeline.examples())
                    } catch (e: Throwable) {  // e.g. the SDK cannot start: never block the game, never show the error
                        _events.tryEmit(EngineEvent.Notice("Không bật được ${dev.screentrans.core.llm.NAMES[c.engine] ?: c.engine} — dùng model trên máy."))
                        null
                    }
                    b.pipeline.setEngine(remote)
                    activeModelId = b.pipeline.activeModelId
                    _events.tryEmit(EngineEvent.Done(job.id, emptyList()))
                    return
                }
                null -> Unit
            }
            val live = job.liveParagraphs
            if (live != null) {
                runLiveTranslate(b, job.id, live, job.liveSpeaker)
                return
            }
            val lines = b.ocr(requireNotNull(job.image) { "job without image" })
            fun perRegion() = job.regions.map { r ->
                Postprocess.run(lines.filter { l ->
                    // the line's centre on screen (tilted lines are boxed in their tilted frame)
                    val (cx, cy) = screentrans.text.Deskew.unrotate(l.left + l.width / 2, l.top + l.height / 2, l.angle)
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

    private fun runLiveTranslate(b: EngineBundle<I>, jobId: Int, groups: List<List<Paragraph>>, speaker: String? = null) {
        val sizes = groups.map { it.size }
        fun regroup(segs: List<Segment>): List<List<Segment>> {
            var i = 0
            return sizes.map { n -> segs.subList(i, i + n).also { i += n } }
        }
        var last: List<List<Segment>> = groups.map { emptyList() }
        for (segs in b.pipeline.iterSentences(groups.flatten(), speaker)) {
            last = regroup(segs)
            _events.tryEmit(EngineEvent.Partial(jobId, last))
        }
        _events.tryEmit(EngineEvent.Done(jobId, last.flatten()))
    }
}
