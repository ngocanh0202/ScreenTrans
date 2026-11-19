package screentrans.text

import com.google.gson.JsonParser

/** Port of windows/app/glossary.py: keep/map terms hidden behind [i] placeholders around the translator. */
data class Entry(val source: String, val keep: Boolean, val target: String?, val caseSensitive: Boolean) {
    val value: String? get() = if (keep) null else target
}

/** Not thread-safe: one Pipeline (and its glossary) is used from a single worker thread. */
class Glossary(entries: List<Entry>) {
    private val exact = HashMap<String, Pair<Int, Entry>>()
    private val folded = HashMap<String, Pair<Int, Entry>>()
    private var pattern: Regex? = null
    private val user = entries.toMutableList()  // loaded + user-added entries (not tracker terms): the digest
    private var nextUserPriority = -1

    init {
        entries.forEachIndexed { prio, e ->  // earlier entries have priority
            if (e.caseSensitive) exact.putIfAbsent(e.source, prio to e)
            else folded.putIfAbsent(e.source.lowercase(), prio to e)
        }
        compile()
    }

    private fun compile() {
        val sources = (exact.keys + folded.values.map { it.second.source }).toSet().sortedByDescending { it.length }
        pattern = if (sources.isEmpty()) null
        else Regex("(?<![\\p{L}\\p{M}\\p{N}_])(?:" + sources.joinToString("|") { Regex.escape(it) } + ")(?![\\p{L}\\p{M}\\p{N}_])", RegexOption.IGNORE_CASE)
    }

    fun addKeep(term: String) {
        if (term in exact || term.lowercase() in folded) return
        exact[term] = AUTO_PRIORITY to Entry(term, true, null, true)
        compile()
    }

    /** A term the user added while correcting: keep ([target] null/blank) or map; wins over every entry. */
    fun addEntry(source: String, target: String?) {
        val src = source.trim()
        if (src.isEmpty()) return
        val e = Entry(src, target.isNullOrBlank(), target?.takeIf { it.isNotBlank() }, true)
        exact[src] = nextUserPriority-- to e
        user.add(e)
        compile()
    }

    /** 12-hex fingerprint of the loaded/user entries; part of the cache key so edits invalidate it. */
    fun digest(): String {
        val rows = user.map { listOf(it.source, if (it.keep) "keep" else "map", it.target ?: "", it.caseSensitive).joinToString(SEP) }.sorted()
        val bytes = java.security.MessageDigest.getInstance("SHA-1").digest(rows.joinToString(ROW).toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }.take(12)
    }

    private fun lookup(matched: String): Entry? =
        listOfNotNull(exact[matched], folded[matched.lowercase()]).minByOrNull { it.first }?.second

    /** Entries that occur in [texts] (same matching as [protect]): source -> target, null = keep as is. */
    fun termsIn(texts: List<String>): Map<String, String?> {
        val p = pattern ?: return emptyMap()
        val found = LinkedHashMap<String, String?>()
        for (t in texts) for (m in p.findAll(t)) {
            val e = lookup(m.value) ?: continue
            if (e.source !in found) found[e.source] = e.value
        }
        return found
    }

    fun protect(text: String): Pair<String, List<String>> {
        val p = pattern ?: return text to emptyList()
        val values = mutableListOf<String>()
        val out = p.replace(text) { m ->
            val entry = lookup(m.value)
            if (entry == null) m.value  // case-sensitive entry matched with the wrong case
            else {
                values.add(entry.value ?: m.value)
                PLACEHOLDER.format(values.size - 1)
            }
        }
        return out to values
    }

    fun restore(text: String, values: List<String>): String? {
        val found = PLACEHOLDER_ANY.findAll(text).map { it.groupValues[1].toInt() }.toList().sorted()
        if (found != values.indices.toList()) return null
        return PLACEHOLDER_ANY.replace(text) { values[it.groupValues[1].toInt()] }
    }

    companion object {
        /** Survived 10/10 through vinai and 7/10 through opus (Phase 1); "⟦i⟧" was dropped. */
        const val PLACEHOLDER = "[%d]"
        private val PLACEHOLDER_ANY = Regex("\\[(\\d+)]")
        const val AUTO_PRIORITY = 1_000_000
        private const val SEP = "\u0001"
        private const val ROW = "\n"

        /** JSON glossaries in priority order (game first, common last). */
        fun load(vararg json: String): Glossary = Glossary(json.flatMap { doc ->
            JsonParser.parseString(doc).asJsonObject["entries"].asJsonArray.map { e ->
                val o = e.asJsonObject
                Entry(
                    o["source"].asString,
                    o["type"].asString == "keep",
                    o["target"]?.asString,
                    o["case_sensitive"]?.asBoolean ?: true,
                )
            }
        })
    }
}

/** Capitalized, non-sentence-initial, uncommon words seen in minCount distinct sentences become keep terms. */
class ProperNounTracker(private val commonWords: Set<String>, private val minCount: Int = 3) {
    private val counts = HashMap<String, Int>()
    private val reported = HashSet<String>()
    private val seen = HashSet<String>()

    fun observe(sentence: String): List<String> {
        val key = normalizeText(sentence)
        if (!seen.add(key)) return emptyList()
        val out = mutableListOf<String>()
        for (word in WORD.findAll(sentence).map { it.value }.drop(1)) {
            if (!word[0].isUpperCase() || word.lowercase() in commonWords) continue
            val n = (counts[word] ?: 0) + 1
            counts[word] = n
            if (n >= minCount && reported.add(word)) out.add(word)
        }
        return out
    }

    private companion object {
        val WORD = Regex("[A-Za-z][A-Za-z'\\-]*")
    }
}
