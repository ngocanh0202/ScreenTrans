package screentrans.text

/** One batch of sentences in, one translation per sentence out (blank in -> ""). */
fun interface SentenceTranslator {
    fun translate(texts: List<String>): List<String>
}

/** Unicode whitespace like Python str.split; written out because Android's ICU regex lacks the U inline flag. */
val UNICODE_WS = Regex("[\\s\\p{Z}\\u0085\\u001c-\\u001f]+")

fun normalizeText(text: String): String = text.trim().split(UNICODE_WS).filter { it.isNotEmpty() }.joinToString(" ")

/** In-memory LRU keyed by (model id, normalized sentence). */
class TranslationCache(private val maxItems: Int) {
    private val map = object : LinkedHashMap<String, String>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, String>?) = size > maxItems
    }

    private fun key(model: String, text: String) = model + "\u0000" + normalizeText(text)
    fun get(model: String, text: String): String? = map[key(model, text)]
    fun put(model: String, text: String, translation: String) {
        map[key(model, text)] = translation
    }
}

/** Split text over `limit` tokens at , ; : first, then between words (port of ct2.split_long). */
fun splitLong(text: String, countTokens: (String) -> Int, limit: Int = 150): List<String> {
    if (countTokens(text) <= limit) return listOf(text)
    val out = mutableListOf<String>()
    var current = ""
    for (piece in text.split(Regex("(?<=[,;:])\\s+"))) {
        val candidate = "$current $piece".trim()
        if (countTokens(candidate) <= limit) {
            current = candidate
            continue
        }
        if (current.isNotEmpty()) out.add(current)
        if (countTokens(piece) <= limit) {
            current = piece
            continue
        }
        current = ""
        for (word in piece.split(" ").filter { it.isNotEmpty() }) {
            val cand = "$current $word".trim()
            if (current.isNotEmpty() && countTokens(cand) > limit) {
                out.add(current)
                current = word
            } else {
                current = cand
            }
        }
    }
    if (current.isNotEmpty()) out.add(current)
    return out
}

/**
 * A model stuck in a loop ("may may may may"): a word repeated 3+ times in a row is kept once
 * (Vietnamese doubles such as "từ từ" stay). Same as windows/app/pipeline.collapse_repeats.
 */
fun collapseRepeats(text: String): String {
    val words = text.split(" ")
    val out = mutableListOf<String>()
    var i = 0
    while (i < words.size) {
        var j = i
        while (j + 1 < words.size && words[i].isNotEmpty() && words[j + 1].equals(words[i], ignoreCase = true)) j++
        if (j - i < 2) out.addAll(words.subList(i, j + 1)) else out.add(words[i])
        i = j + 1
    }
    return out.joinToString(" ")
}

data class Segment(
    val kind: Kind,
    val source: String,
    val translation: String?,
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
)

/** Port of windows/app/pipeline.py (without OCR). Use one instance from a single thread. */
class Pipeline(
    private val translator: SentenceTranslator,
    private val modelId: String,
    private var glossary: Glossary,
    private val cache: TranslationCache,
    private val tracker: ProperNounTracker? = null,
    private val modelVersion: String = "0",
    overrides: Map<String, String> = emptyMap(),
) {
    private val overrides = HashMap<String, String>().apply { overrides.forEach { (k, v) -> put(normalizeText(k), v) } }

    /** Cache key prefix: a new model version or glossary edit must not reuse old translations. */
    val cacheNs: String get() = "$modelId@$modelVersion#${glossary.digest()}"

    /** Switch to another game's glossary and the user's translations for it. */
    fun setGame(glossary: Glossary, overrides: Map<String, String>) {
        this.glossary = glossary
        this.overrides.clear()
        overrides.forEach { (k, v) -> this.overrides[normalizeText(k)] = v }
    }

    /** The user fixed a translation: use it from now on, before cache and model. */
    fun correct(source: String, corrected: String) {
        overrides[normalizeText(source)] = corrected
    }

    /** A glossary term the user added (target null/blank = keep the source unchanged). */
    fun addTerm(source: String, target: String?) = glossary.addEntry(source, target)

    /** The user's translations (to save into the game profile). */
    fun overrides(): Map<String, String> = HashMap(overrides)

    private fun observe(sentences: List<String>) {
        val t = tracker ?: return
        for (s in sentences) for (term in t.observe(s)) glossary.addKeep(term)
    }

    private fun translateSentences(sentences: List<String>): Map<String, String> {
        val done = HashMap<String, String>()
        val todo = mutableListOf<String>()
        val ns = cacheNs
        for (s in sentences.distinct()) {
            val fixed = overrides[normalizeText(s)]
            if (fixed != null) {  // the user's own translation wins over cache and model
                done[s] = fixed
                continue
            }
            val hit = cache.get(ns, s)
            if (hit != null) done[s] = hit else todo.add(s)
        }
        if (todo.isEmpty()) return done
        val protected = todo.map { glossary.protect(it) }
        val outputs = translator.translate(protected.map { it.first })
        val retry = mutableListOf<String>()
        for ((i, s) in todo.withIndex()) {
            val values = protected[i].second
            val restored = (if (values.isEmpty()) outputs[i] else glossary.restore(outputs[i], values))?.let(::collapseRepeats)
            if (restored == null) retry.add(s) else done[s] = restored
        }
        if (retry.isNotEmpty()) {  // the model damaged a placeholder: translate without glossary protection
            translator.translate(retry).forEachIndexed { i, out -> done[retry[i]] = out }
        }
        for (s in todo) if (s !in retry) cache.put(ns, s, done.getValue(s))  // never cache the degraded retry
        return done
    }

    private fun segment(p: Paragraph, translated: Map<String, String>) =
        if (p.kind == Kind.NAME) Segment(Kind.NAME, p.text, null, p.left, p.top, p.right, p.bottom)
        else Segment(Kind.TEXT, p.text, p.sentences.joinToString(" ") { translated.getValue(it) }, p.left, p.top, p.right, p.bottom)

    /** One translator batch for every sentence (region mode). */
    fun translateParagraphs(paragraphs: List<Paragraph>): List<Segment> {
        val sentences = paragraphs.filter { it.kind == Kind.TEXT }.flatMap { it.sentences }
        observe(sentences)
        val translated = if (sentences.isEmpty()) emptyMap() else translateSentences(sentences)
        return paragraphs.map { segment(it, translated) }
    }

    /** Live: after each translated sentence yield all segments; untranslated sentences show "…". */
    fun iterSentences(paragraphs: List<Paragraph>): Sequence<List<Segment>> = sequence {
        val textSentences = paragraphs.filter { it.kind == Kind.TEXT }.flatMap { it.sentences }
        observe(textSentences)
        val done = HashMap<String, String>()
        fun snapshot() = paragraphs.map { p ->
            if (p.kind == Kind.NAME) Segment(Kind.NAME, p.text, null, p.left, p.top, p.right, p.bottom)
            else Segment(Kind.TEXT, p.text, p.sentences.joinToString(" ") { done[it] ?: "…" }, p.left, p.top, p.right, p.bottom)
        }
        val order = textSentences.distinct()
        if (order.isEmpty()) {
            yield(snapshot())
            return@sequence
        }
        for (s in order) {
            done.putAll(translateSentences(listOf(s)))
            yield(snapshot())
        }
    }

    /** Each paragraph as soon as it is translated (full-screen mode shows blocks progressively). */
    fun iterSegments(paragraphs: List<Paragraph>): Sequence<Segment> = sequence {
        observe(paragraphs.filter { it.kind == Kind.TEXT }.flatMap { it.sentences })
        for (p in paragraphs) {
            val translated = if (p.kind == Kind.TEXT && p.sentences.isNotEmpty()) translateSentences(p.sentences) else emptyMap()
            yield(segment(p, translated))
        }
    }
}
