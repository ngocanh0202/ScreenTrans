package dev.screentrans.core.ui

import dev.screentrans.core.llm.DEFAULT_MODELS
import screentrans.text.Terms

/**
 * Picking words of a source sentence by touch (correction view): the first tap selects a word, the next taps in
 * the same sentence extend from it, tapping the single selected word again clears. Windows does the same with
 * click / shift-click / drag (windows/app/gui/word_picker.py).
 */
class WordSelection {
    var sentence = -1
        private set
    private var anchor = -1
    private var from = -1
    private var to = -1

    fun tap(s: Int, i: Int) {
        when {
            s != sentence || anchor < 0 -> { sentence = s; anchor = i; from = i; to = i }
            from == to && i == from -> clear()
            else -> { from = minOf(anchor, i); to = maxOf(anchor, i) }
        }
    }

    fun clear() {
        sentence = -1; anchor = -1; from = -1; to = -1
    }

    fun isSelected(s: Int, i: Int) = s == sentence && i in from..to

    /** The selected words as a term (outer punctuation removed), "" when nothing is selected. */
    fun text(tokens: List<List<String>>): String =
        if (sentence < 0 || from < 0) "" else Terms.span(tokens[sentence], from, to)
}

/** Terms added in the correction view: one per source (any case), newest last. */
class TermList {
    private val list = mutableListOf<Pair<String, String?>>()
    val items: List<Pair<String, String?>> get() = list.toList()

    fun add(source: String, target: String?) {
        val src = source.trim()
        if (src.isEmpty()) return
        list.removeAll { it.first.equals(src, ignoreCase = true) }
        list.add(src to target?.trim()?.takeIf { it.isNotEmpty() })
    }

    fun remove(source: String) {
        list.removeAll { it.first == source }
    }
}

object LlmPrefsLogic {
    /** The stored model names after the user typed [typed] for [engine]: empty or the default is not a choice. */
    fun models(current: Map<String, String>, engine: String, typed: String): Map<String, String> {
        val m = typed.trim()
        return if (m.isEmpty() || m == DEFAULT_MODELS[engine]) current - engine else current + (engine to m)
    }
}
