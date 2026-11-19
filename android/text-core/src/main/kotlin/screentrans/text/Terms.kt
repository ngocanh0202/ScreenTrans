package screentrans.text

/** Picking glossary terms in the correction view: shared/fixtures/terms (same as windows/app/text/terms.py). */
object Terms {
    private const val PUNCT = ".,!?;:\"'()[]…“”‘’—-"
    private const val CLOSERS = "\"'”’)]"
    private val ABBREVIATIONS = setOf("mr", "mrs", "ms", "dr", "st", "mt", "jr", "sr")

    fun tokens(sentence: String): List<String> = sentence.trim().split(UNICODE_WS).filter { it.isNotEmpty() }

    private fun core(token: String) = token.trim { it in PUNCT }

    /** Tokens from..to (inclusive) as a term: outer punctuation removed ("Ms." keeps its dot). */
    fun span(tokens: List<String>, from: Int, to: Int): String {
        val text = tokens.subList(from, to + 1).joinToString(" ").trimStart { it in PUNCT }
        val stripped = text.trimEnd { it in PUNCT }
        val last = core(tokens[to]).lowercase()
        return if (last in ABBREVIATIONS && text.substring(stripped.length).startsWith(".")) "$stripped." else stripped
    }

    private fun endsRun(token: String): Boolean {
        val t = token.trimEnd { it in CLOSERS }
        if (t.endsWith(",") || t.endsWith(";") || t.endsWith(":") || t.endsWith("!") || t.endsWith("?") || t.endsWith("…")) return true
        return t.endsWith(".") && core(token).lowercase() !in ABBREVIATIONS
    }

    private fun capitalized(token: String): Boolean {
        val c = core(token)
        return c.isNotEmpty() && c[0].isUpperCase() && c != "I"
    }

    /** Likely names in the sentences (to keep untranslated), first seen first, without the known ones. */
    fun suggestNames(sentences: List<String>, common: Set<String>, known: Set<String>): List<String> {
        val knownLower = known.map { it.lowercase() }.toSet()
        val out = mutableListOf<String>()
        val seen = HashSet<String>()

        fun consider(toks: List<String>, run0: List<Int>) {
            var run = run0
            if (run.isNotEmpty() && run[0] == 0) {  // sentence start: "The", "Where", "Ask" are not part of a name
                while (run.isNotEmpty()) {
                    val c = core(toks[run[0]]).lowercase()
                    if (c in common && c !in ABBREVIATIONS) run = run.drop(1) else break
                }
            }
            if (run.isEmpty() || run.all { core(toks[it]).lowercase() in common }) return
            val name = span(toks, run.first(), run.last())
            val key = name.lowercase()
            if (key !in knownLower && seen.add(key)) out.add(name)
        }

        for (sentence in sentences) {
            val toks = tokens(sentence)
            var run = mutableListOf<Int>()
            for ((i, tok) in toks.withIndex()) {
                if (capitalized(tok)) {
                    run.add(i)
                    if (endsRun(tok)) {
                        consider(toks, run)
                        run = mutableListOf()
                    }
                } else {
                    consider(toks, run)
                    run = mutableListOf()
                }
            }
            consider(toks, run)
        }
        return out
    }
}
