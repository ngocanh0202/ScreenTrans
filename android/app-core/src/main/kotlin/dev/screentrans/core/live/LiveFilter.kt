package dev.screentrans.core.live

import screentrans.text.Kind
import screentrans.text.Paragraph

/** Live: leave OCR noise and UI labels out before translating — port of windows/app/live/filter.py. */
object LiveFilter {
    private val END = Regex("[.!?…][\"'”’)]*$")

    fun worthTranslating(p: Paragraph): Boolean {
        if (p.kind == Kind.NAME) return true
        val text = p.text.trim()
        val chars = text.filter { !it.isWhitespace() }
        val letters = chars.count { it.isLetter() }
        val ended = END.containsMatchIn(text)  // "Hi.", "No!" are real (short) lines of dialogue
        if (letters < (if (ended) 2 else 3) || letters < 0.5 * chars.length) return false
        val words = text.split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (words.size <= 3 && words.any { w -> w.any { it.isLetter() } && w.any { it.isDigit() } }) return false  // "St3loo 3,": OCR noise; a longer line with one misread word stays
        if (words.size <= 2 && words.any { w -> w.trim('.', ',', ':', ';', '!', '?').let { it.isNotEmpty() && it.all(Char::isDigit) } }) return false
        if (words.size == 1 && !ended) return false  // "AUTO", "SKIP": UI labels
        if (words.none { w -> w.count { it.isLetter() } >= 2 }) return false  // "X X X"
        if (p.lineHeight > 0 && (p.right - p.left) < 3 * p.lineHeight) return false  // vertical text / noise
        return true
    }
}
