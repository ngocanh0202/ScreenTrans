package dev.screentrans.core.llm

import com.google.gson.Gson
import com.google.gson.JsonParser
import screentrans.text.LlmPrompt
import screentrans.text.RemoteEngine
import screentrans.text.SentenceTranslator
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.time.LocalDate
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/** Characters sent to remote engines today (daily limit): dir/usage.json, written atomically. */
open class UsageStore(dir: File, private val clock: () -> LocalDate = { LocalDate.now() }) {
    private val file = File(dir, "usage.json")

    fun today(): String = clock().toString()

    fun used(): Int = try {
        val o = JsonParser.parseString(file.readText()).asJsonObject
        if (o["date"].asString == today()) o["chars"].asInt else 0
    } catch (e: Exception) {
        0
    }

    fun allows(chars: Int, limit: Int) = used() + chars <= limit

    open fun add(chars: Int) {
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        tmp.writeText(Gson().toJson(mapOf("date" to today(), "chars" to used() + chars)))
        if (!tmp.renameTo(file)) {
            file.delete()
            tmp.renameTo(file)
        }
    }
}

/** The last lines of each game's dialogue (speaker, line): dir/llm_context/<game>.json. */
class ContextStore(dir: File) {
    private val folder = File(dir, "llm_context")

    private fun file(game: String): File {
        val safe = game.replace(Regex("[^A-Za-z0-9._-]+"), "_").trim('.', '_').take(60).ifEmpty { "game" }
        val digest = MessageDigest.getInstance("SHA-1").digest(game.toByteArray()).joinToString("") { "%02x".format(it) }.take(8)
        return File(folder, "$safe-$digest.json")
    }

    fun load(game: String): List<Pair<String?, String>> = try {
        JsonParser.parseString(file(game).readText()).asJsonArray.mapNotNull { e ->
            val a = e.asJsonArray
            val text = a[1].takeIf { it.isJsonPrimitive }?.asString ?: return@mapNotNull null
            (if (a[0].isJsonNull) null else a[0].asString) to text
        }.takeLast(LlmPrompt.CONTEXT_MAX)
    } catch (e: Exception) {
        emptyList()
    }

    fun save(game: String, lines: List<Pair<String?, String>>) {
        try {
            folder.mkdirs()
            val f = file(game)
            val tmp = File(f.path + ".tmp")
            tmp.writeText(Gson().toJson(lines.takeLast(LlmPrompt.CONTEXT_MAX).map { listOf(it.first, it.second) }))
            if (!tmp.renameTo(f)) {
                f.delete()
                tmp.renameTo(f)
            }
        } catch (e: Exception) {
            // context is a nicety: never fail a translation over it
        }
    }
}

/**
 * Translate with a remote LLM: the game's notes, the user's corrections, the previous lines with their
 * speakers, the glossary terms. [translateCtx] returns null whenever the remote engine cannot be used; the
 * Pipeline then translates with [local]. Same rules as windows/app/translate/llm.py. Use from one thread.
 */
class LlmTranslator(
    private val engine: String,
    private val client: LlmClient,
    override val local: SentenceTranslator,
    override val localModelId: String,
    private val usage: UsageStore,
    var dailyLimit: Int,
    private val notify: (String) -> Unit,
    private val clock: () -> Long = { System.currentTimeMillis() },
    private val contexts: ContextStore? = null,
) : RemoteEngine {
    override val modelId = "$engine:${client.model}"
    var timeoutMs = 6000
    private var context: List<Pair<String?, String>> = emptyList()
    private var speaker: String? = null
    private var game: String? = null
    private var notes = ""
    private var examples: List<Pair<String, String>> = emptyList()
    private var blocked = false
    private var retryAt = 0L
    private var failing = false
    private var limitDay = ""

    /** One overall deadline per call (socket timeouts are per step; DNS has none): a late call finishes here. */
    private val pool: ExecutorService = Executors.newCachedThreadPool { r -> Thread(r, "llm-$engine").apply { isDaemon = true } }

    fun setGame(game: String?, notes: String, examples: List<Pair<String, String>>) {
        this.game = game
        this.notes = notes
        this.examples = examples
        context = if (contexts != null && game != null) contexts.load(game) else emptyList()
        blocked = false
        retryAt = 0
        failing = false
    }

    override fun setExamples(examples: List<Pair<String, String>>) {
        this.examples = examples
    }

    override fun setSpeaker(name: String?) {
        speaker = name
    }

    override fun available() = !blocked && clock() >= retryAt && usage.allows(1, dailyLimit)

    override fun translateCtx(texts: List<String>, glossary: Map<String, String?>): List<String>? {
        if (texts.isEmpty()) return emptyList()
        if (blocked || clock() < retryAt) return null
        val chars = texts.sumOf { it.length }
        if (!usage.allows(chars, dailyLimit)) {
            val today = usage.today()
            if (limitDay != today) {
                limitDay = today
                notify("${client.name}: đã tới giới hạn $dailyLimit ký tự hôm nay — dùng model trên máy.")
            }
            return null
        }
        val (system, user) = LlmPrompt.buildMessages(texts, context, speaker, glossary, notes, examples)
        val askedGame = game
        val askedSpeaker = speaker
        try {
            usage.add(chars)  // before the call: a timed-out request is usually still processed (and billed)
        } catch (e: IOException) {
            // usage.json not writable right now: never fail the translation over the counter
        }
        val future = pool.submit<String> { client.complete(system, user, timeoutMs) }
        val reply = try {
            future.get(timeoutMs.toLong(), TimeUnit.MILLISECONDS)
        } catch (e: TimeoutException) {
            future.cancel(true)
            fail(RemoteError("timeout", client.name))
            return null
        } catch (e: java.util.concurrent.ExecutionException) {
            fail(e.cause as? RemoteError ?: RemoteError("server", client.name))  // other errors: their text may hold the key
            return null
        } catch (e: Exception) {
            fail(RemoteError("server", client.name))
            return null
        }
        val out = LlmPrompt.parseReply(reply, texts.size) ?: return null  // this batch only
        failing = false
        val lines = texts.map { askedSpeaker to it }
        val saved = if (askedGame == game) {
            context = (context + lines).takeLast(LlmPrompt.CONTEXT_MAX)
            context
        } else {
            (if (contexts != null && askedGame != null) contexts.load(askedGame) else emptyList()) + lines
        }
        if (contexts != null && askedGame != null) contexts.save(askedGame, saved)
        return out
    }

    private fun fail(e: RemoteError) {
        if (e.kind == "auth") {
            blocked = true
            notify("${client.name}: sai key hoặc hết quyền — mở Cài đặt để sửa. Đang dùng model trên máy.")
            return
        }
        retryAt = clock() + RETRY_AFTER_MS
        if (!failing) {
            failing = true
            notify("${client.name}: ${REASONS[e.kind] ?: e.kind} — dùng model trên máy.")
        }
    }

    fun close() {
        pool.shutdownNow()
    }

    private companion object {
        const val RETRY_AFTER_MS = 30_000L
        val REASONS = mapOf("timeout" to "quá thời gian", "network" to "không kết nối được", "server" to "server lỗi",
            "quota" to "hết hạn mức / quá nhiều yêu cầu", "bad_reply" to "trả lời không hợp lệ")
    }
}
