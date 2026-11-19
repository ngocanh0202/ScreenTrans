package dev.screentrans.core.live

/** Port of windows/app/live/sentences.py — rules in shared/fixtures/live_sentences/README.md. */
object SentenceGate {
    /**
     * Two reads of the same text on an animated background differ in letters OCR confuses (I/l/1/|, 0/O) or in
     * case: the same key. A different length is a real change (text still typing). Same as sentences.ocr_key.
     */
    fun ocrKey(text: String): String = screentrans.text.normalizeText(text).lowercase()
        .map { c -> when (c) { 'i', '1', '|' -> 'l'; '0' -> 'o'; else -> c } }.joinToString("")

    private val END = Regex("(?:[.!?]|…)[\"'”’)」』]*$")

    /** Number of leading sentences that are finished and may be translated and shown. */
    fun done(sentences: List<String>, previous: List<String>?, final: Boolean): Int {
        val n = sentences.size
        if (n == 0 || final) return n
        val last = sentences.last().trim()
        if (END.containsMatchIn(last) && previous != null && previous.size == n && ocrKey(previous.last()) == ocrKey(last)) return n
        return n - 1
    }
}
