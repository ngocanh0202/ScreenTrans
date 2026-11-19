package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.Gravity
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import dev.screentrans.core.ui.TermList
import dev.screentrans.core.ui.WordSelection
import screentrans.text.Kind
import screentrans.text.Segment
import screentrans.text.Terms

/** One fix: the source sentence, the machine translation, the user's translation. */
data class Fix(val source: String, val machine: String, val corrected: String)

/**
 * Correct translations (AGENT.md §9): one edit box per sentence. Glossary terms are picked, not typed: tap a
 * word of a source sentence (tap more words to extend), then "Giữ nguyên" or "Dịch cố định" (only the
 * Vietnamese is typed); added terms are chips (tap to remove); likely names are suggested (tap to keep).
 * Shown as a focusable overlay so the keyboard works over the game. Same as windows/app/gui/correct_dialog.py.
 */
@SuppressLint("ViewConstructor")
class CorrectView(
    context: Context,
    segments: List<Segment>,
    common: Set<String>,
    known: Set<String>,
    private val onDone: (fixes: List<Fix>, terms: List<Pair<String, String?>>) -> Unit,
    private val onCancel: () -> Unit,
) : LinearLayout(context) {
    private val blue = Color.rgb(37, 99, 235)
    private val chipIdle = Color.argb(45, 255, 255, 255)
    private val rows = segments.filter { it.kind == Kind.TEXT && !it.translation.isNullOrEmpty() }
    private val tokens = rows.map { Terms.tokens(it.source) }
    private val selection = WordSelection()
    private val terms = TermList()
    private val wordViews = tokens.mapIndexed { s, words ->
        words.mapIndexed { i, w -> chip(w, chipIdle) { selection.tap(s, i); refreshSelection() } }
    }
    private val edits = rows.map { seg ->
        EditText(context).apply {
            setText(seg.translation)
            setTextColor(Color.WHITE)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
    }
    private val selectedLabel = TextView(context).apply { setTextColor(Color.rgb(170, 170, 170)); textSize = 13f }
    private val keep = button("Giữ nguyên") { addPicked(null) }
    private val target = EditText(context).apply {
        hint = "Bản dịch cố định"
        setHintTextColor(Color.GRAY)
        setTextColor(Color.WHITE)
        inputType = InputType.TYPE_CLASS_TEXT
        imeOptions = EditorInfo.IME_ACTION_DONE
        setOnEditorActionListener { _, _, _ -> addPicked(text.toString()); true }  // Enter adds, never saves
    }
    private val fixed = button("Dịch cố định") { addPicked(target.text.toString()) }
    private val termChips = FlowLayout(context)
    private val suggestionChips = FlowLayout(context)

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply {
            setColor(Color.argb(240, 20, 20, 24))
            cornerRadius = context.dp(10).toFloat()
        }
        setPadding(context.dp(14), context.dp(10), context.dp(14), context.dp(8))
        addView(TextView(context).apply {
            text = "Sửa bản dịch (lần sau gặp đúng câu này sẽ dùng bản của bạn)"
            setTextColor(Color.WHITE)
        })
        val list = LinearLayout(context).apply { orientation = VERTICAL }
        rows.indices.forEach { s ->
            list.addView(FlowLayout(context).apply { wordViews[s].forEach { addView(it) } })
            list.addView(edits[s])
        }
        list.addView(selectedLabel)
        list.addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(keep)
            addView(target, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
            addView(fixed)
        })
        list.addView(caption("Thuật ngữ đã thêm (chạm để xóa):"))
        list.addView(termChips)
        val suggested = Terms.suggestNames(rows.map { it.source }, common, known)
        if (suggested.isNotEmpty()) {
            list.addView(caption("Gợi ý tên riêng (chạm để giữ nguyên):"))
            list.addView(suggestionChips)
            suggested.forEach { name ->
                lateinit var c: TextView
                c = chip("$name  +", chipIdle) { terms.add(name, null); suggestionChips.removeView(c); refreshTerms() }
                suggestionChips.addView(c)
            }
        }
        addView(ScrollView(context).apply { addView(list) }, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
        val buttons = LinearLayout(context).apply { orientation = HORIZONTAL }
        buttons.addView(button("Hủy") { onCancel() })
        buttons.addView(button("Lưu") { onDone(fixes(), terms.items) })
        addView(buttons)
        refreshSelection()
    }

    private fun addPicked(targetText: String?) {
        val src = selection.text(tokens)
        if (src.isEmpty() || (targetText != null && targetText.isBlank())) return  // "Dịch cố định" needs the Vietnamese
        terms.add(src, targetText)
        target.setText("")
        selection.clear()
        refreshSelection()
        refreshTerms()
    }

    private fun refreshSelection() {
        wordViews.forEachIndexed { s, views ->
            views.forEachIndexed { i, v -> (v.background as GradientDrawable).setColor(if (selection.isSelected(s, i)) blue else chipIdle) }
        }
        val text = selection.text(tokens)
        selectedLabel.text = if (text.isEmpty()) "Chạm chữ ở câu gốc (chạm thêm để chọn cả cụm) để thêm thuật ngữ." else "Đã chọn: “$text”"
        listOf(keep, fixed, target).forEach { it.isEnabled = text.isNotEmpty(); it.alpha = if (text.isNotEmpty()) 1f else 0.4f }
    }

    private fun refreshTerms() {
        termChips.removeAllViews()
        terms.items.forEach { (src, dst) ->
            termChips.addView(chip(if (dst == null) "$src (giữ nguyên)  ✕" else "$src → $dst  ✕", chipIdle) {
                terms.remove(src)
                refreshTerms()
            })
        }
    }

    private fun chip(label: String, color: Int, action: () -> Unit) = TextView(context).apply {
        text = label
        textSize = 14f
        setTextColor(Color.WHITE)
        setPadding(context.dp(7), context.dp(5), context.dp(7), context.dp(5))
        background = GradientDrawable().apply { setColor(color); cornerRadius = context.dp(6).toFloat() }
        setOnClickListener { action() }
    }

    private fun caption(t: String) = TextView(context).apply {
        text = t; textSize = 12f; setTextColor(Color.rgb(160, 160, 170)); setPadding(0, context.dp(8), 0, context.dp(4))
    }

    private fun button(label: String, action: () -> Unit) = Button(context).apply {
        text = label
        isAllCaps = false
        setTextColor(Color.WHITE)
        setBackgroundColor(Color.TRANSPARENT)
        setOnClickListener { action() }
    }

    private fun fixes(): List<Fix> = rows.mapIndexedNotNull { i, seg ->
        val text = edits[i].text.toString().trim()
        if (text.isEmpty() || text == seg.translation) null else Fix(seg.source, seg.translation ?: "", text)
    }
}
