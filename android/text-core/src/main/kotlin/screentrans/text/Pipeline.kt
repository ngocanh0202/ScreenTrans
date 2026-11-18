package screentrans.text

/** One batch of sentences in, one translation per sentence out (blank in -> ""). */
fun interface SentenceTranslator {
    fun translate(texts: List<String>): List<String>
}

fun normalizeText(text: String): String = text.trim().split(Regex("(?U)\\s+")).filter { it.isNotEmpty() }.joinToString(" ")

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
    private val glossary: Glossary,
    private val cache: TranslationCache,
    private val tracker: ProperNounTracker? = null,
) {
    private fun observe(sentences: List<String>) {
        val t = tracker ?: return
        for (s in sentences) for (term in t.observe(s)) glossary.addKeep(term)
    }

    private fun translateSentences(sentences: List<String>): Map<String, String> {
        val done = HashMap<String, String>()
        val todo = mutableListOf<String>()
        for (s in sentences.distinct()) {
            val hit = cache.get(modelId, s)
            if (hit != null) done[s] = hit else todo.add(s)
        }
        if (todo.isEmpty()) return done
        val protected = todo.map { glossary.protect(it) }
        val outputs = translator.translate(protected.map { it.first })
        val retry = mutableListOf<String>()
        for ((i, s) in todo.withIndex()) {
            val values = protected[i].second
            val restored = if (values.isEmpty()) outputs[i] else glossary.restore(outputs[i], values)
            if (restored == null) retry.add(s) else done[s] = restored
        }
        if (retry.isNotEmpty()) {  // the model damaged a placeholder: translate without glossary protection
            translator.translate(retry).forEachIndexed { i, out -> done[retry[i]] = out }
        }
        for (s in todo) if (s !in retry) cache.put(modelId, s, done.getValue(s))  // never cache the degraded retry
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

    /** Each paragraph as soon as it is translated (full-screen mode shows blocks progressively). */
    fun iterSegments(paragraphs: List<Paragraph>): Sequence<Segment> = sequence {
        observe(paragraphs.filter { it.kind == Kind.TEXT }.flatMap { it.sentences })
        for (p in paragraphs) {
            val translated = if (p.kind == Kind.TEXT && p.sentences.isNotEmpty()) translateSentences(p.sentences) else emptyMap()
            yield(segment(p, translated))
        }
    }
}
