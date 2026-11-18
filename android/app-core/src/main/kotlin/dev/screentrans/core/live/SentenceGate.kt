package dev.screentrans.core.live

/** Port of windows/app/live/sentences.py — rules in shared/fixtures/live_sentences/README.md. */
object SentenceGate {
    private val END = Regex("(?:[.!?]|…)[\"'”’)」』]*$")

    /** Number of leading sentences that are finished and may be translated and shown. */
    fun done(sentences: List<String>, previous: List<String>?, final: Boolean): Int {
        val n = sentences.size
        if (n == 0 || final) return n
        val last = sentences.last().trim()
        if (END.containsMatchIn(last) && previous != null && previous.size == n && previous.last().trim() == last) return n
        return n - 1
    }
}
