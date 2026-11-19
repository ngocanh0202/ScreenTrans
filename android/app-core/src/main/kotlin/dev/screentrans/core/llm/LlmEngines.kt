package dev.screentrans.core.llm

import screentrans.text.SentenceTranslator
import java.io.File
import java.security.MessageDigest

/** Non-secret remote-engine settings of a game (the key comes from [KeyProvider]). */
data class LlmSettings(val model: String = "", val url: String = "", val dailyLimit: Int = 50_000, val notes: String = "")

/** Saved API keys (Android Keystore in the app); "" when none. */
fun interface KeyProvider {
    fun key(engine: String): String
}

/**
 * The game's translation engine: null for the on-device model, else one [LlmTranslator] per engine / model /
 * URL / key, reused across games (each game gets its notes, corrections and saved context). Same as the Windows
 * worker's _use_engine. Use from the engine thread.
 */
class LlmEngines(
    private val dir: File,
    private val keys: KeyProvider,
    private val local: SentenceTranslator,
    private val localModelId: String,
    private val clientFactory: (engine: String, key: String, model: String, url: String) -> LlmClient =
        { e, k, m, u -> makeClient(e, k, m, u) },
) {
    var notify: (String) -> Unit = {}
    private val translators = HashMap<List<Any>, LlmTranslator>()
    private val noKeyTold = HashSet<String>()
    private val contexts = ContextStore(dir)
    private val usage = UsageStore(dir)

    fun use(game: String?, engine: String, s: LlmSettings, examples: List<Pair<String, String>>): LlmTranslator? {
        if (engine !in NAMES) return null
        val key = keys.key(engine)
        if (key.isEmpty()) {
            if (noKeyTold.add(engine)) notify("Chưa nhập key cho ${NAMES[engine]} — dùng model trên máy.")
            return null
        }
        noKeyTold.remove(engine)
        val digest = MessageDigest.getInstance("SHA-256").digest(key.toByteArray()).joinToString("") { "%02x".format(it) }
        val id = listOf(engine, s.model, s.url, digest)
        val tr = translators.getOrPut(id) {
            LlmTranslator(engine, clientFactory(engine, key, s.model, s.url), local, localModelId, usage, s.dailyLimit,
                { notify(it) }, contexts = contexts)
        }
        tr.dailyLimit = s.dailyLimit
        tr.setGame(game, s.notes, examples)
        return tr
    }

    fun close() = translators.values.forEach { it.close() }
}
