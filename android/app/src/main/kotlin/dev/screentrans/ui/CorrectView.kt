package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import screentrans.text.Kind
import screentrans.text.Segment

/** One fix: the source sentence, the machine translation, the user's translation. */
data class Fix(val source: String, val machine: String, val corrected: String)

/**
 * Correct translations (AGENT.md §9): one edit box per sentence + glossary terms ("source = target",
 * empty target = keep). Shown as a focusable overlay so the keyboard works over the game.
 */
@SuppressLint("ViewConstructor")
class CorrectView(
    context: Context,
    segments: List<Segment>,
    private val onDone: (fixes: List<Fix>, terms: List<Pair<String, String?>>) -> Unit,
    private val onCancel: () -> Unit,
) : LinearLayout(context) {
    private val rows = segments.filter { it.kind == Kind.TEXT && !it.translation.isNullOrEmpty() }
    private val edits = rows.map { seg ->
        EditText(context).apply {
            setText(seg.translation)
            setTextColor(Color.WHITE)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
    }
    private val terms = EditText(context).apply {
        hint = "Thuật ngữ, mỗi dòng: Arcanist =   (giữ nguyên)   ·   Storm = Bão Tố"
        setHintTextColor(Color.GRAY)
        setTextColor(Color.WHITE)
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        minLines = 2
    }

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
        rows.forEachIndexed { i, seg ->
            list.addView(TextView(context).apply {
                text = seg.source
                setTextColor(Color.rgb(170, 170, 170))
                setTextIsSelectable(true)
            })
            list.addView(edits[i])
        }
        list.addView(terms)
        addView(ScrollView(context).apply { addView(list) }, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
        val buttons = LinearLayout(context).apply { orientation = HORIZONTAL }
        buttons.addView(button("Hủy") { onCancel() })
        buttons.addView(button("Lưu") { onDone(fixes(), parseTerms(terms.text.toString())) })
        addView(buttons)
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

    companion object {
        /** Same rules as windows/app/gui/correct_dialog.parse_terms. */
        fun parseTerms(text: String): List<Pair<String, String?>> = text.lines().mapNotNull { line ->
            val i = line.indexOf('=')
            if (i < 0) return@mapNotNull null
            val src = line.substring(0, i).trim()
            val target = line.substring(i + 1).trim()
            if (src.isEmpty()) null else src to target.ifEmpty { null }
        }
    }
}
