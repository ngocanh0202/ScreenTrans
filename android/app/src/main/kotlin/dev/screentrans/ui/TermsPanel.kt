package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import screentrans.text.TermEdit

/**
 * "📖 Thuật ngữ" (Phase 5): the game's own glossary terms, one row each [từ gốc | dịch thành | ✕], "+ Thêm",
 * Hủy / Lưu. An empty "dịch thành" keeps the source as is. Rows are cleaned (TermEdit.clean) before [onSave].
 * Same as the Windows "Thuật ngữ" window.
 */
@SuppressLint("ViewConstructor")
class TermsPanel(
    context: Context,
    game: String,
    rows: List<TermEdit.Row>,
    private val onSave: (List<TermEdit.Row>) -> Unit,
    private val onClose: () -> Unit,
) : LinearLayout(context) {
    private val idle = Color.argb(45, 255, 255, 255)
    private val list = LinearLayout(context).apply { orientation = VERTICAL }

    private class RowViews(val view: LinearLayout, val source: EditText, val target: EditText, val caseSensitive: Boolean)

    private val rowViews = mutableListOf<RowViews>()

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply { setColor(Color.argb(245, 22, 22, 28)); cornerRadius = context.dp(16).toFloat() }
        val pad = context.dp(12)
        setPadding(pad, pad, pad, pad)
        addView(TextView(context).apply { text = "📖  Thuật ngữ — $game"; textSize = 16f; setTextColor(Color.WHITE) })
        addView(TextView(context).apply {
            text = "Từ gốc tiếng Anh và cách dịch. Để trống \"dịch thành\" = giữ nguyên (tên riêng). Áp dụng ngay khi lưu."
            textSize = 12f; setTextColor(Color.rgb(160, 160, 170)); setPadding(0, context.dp(4), 0, context.dp(6))
        })
        rows.forEach(::addRow)
        if (rows.isEmpty()) addRow(TermEdit.Row("", null))
        addView(ScrollView(context).apply { addView(list) }, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            addView(button("+ Thêm") { addRow(TermEdit.Row("", null)).source.requestFocus() })
            addView(android.view.View(context), LayoutParams(0, 0, 1f))
            addView(button("Hủy") { onClose() })
            addView(button("Lưu") { onSave(TermEdit.clean(current())) })
        })
    }

    private fun addRow(r: TermEdit.Row): RowViews {
        val source = field("Từ gốc", r.source)
        val target = field("Dịch thành (trống = giữ nguyên)", r.target ?: "")
        val view = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(source, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
            addView(target, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        }
        val rv = RowViews(view, source, target, r.caseSensitive)
        view.addView(TextView(context).apply {
            text = "✕"
            textSize = 16f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            background = GradientDrawable().apply { setColor(idle); cornerRadius = context.dp(6).toFloat() }
            setOnClickListener { list.removeView(view); rowViews.remove(rv) }
        }, LayoutParams(context.dp(40), context.dp(40)))
        list.addView(view)
        rowViews.add(rv)
        return rv
    }

    private fun current(): List<TermEdit.Row> =
        rowViews.map { TermEdit.Row(it.source.text.toString(), it.target.text.toString(), it.caseSensitive) }

    private fun field(hint: String, value: String) = EditText(context).apply {
        this.hint = hint
        setHintTextColor(Color.GRAY)
        setTextColor(Color.WHITE)
        textSize = 14f
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        setText(value)
    }

    private fun button(label: String, action: () -> Unit) = Button(context).apply {
        text = label
        isAllCaps = false
        setTextColor(Color.WHITE)
        setBackgroundColor(Color.TRANSPARENT)
        setOnClickListener { action() }
    }
}
