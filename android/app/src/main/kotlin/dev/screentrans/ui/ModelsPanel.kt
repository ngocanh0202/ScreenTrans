package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import dev.screentrans.core.model.ModelRow

/**
 * "🧠 Model" (Phase 5): the published models (Hugging Face) and the ones on the phone, one row each with
 * [Tải / Cập nhật] [Dùng] [Xóa]. The controller downloads and calls [render] with the new rows / progress.
 * Same as the Windows "Quản lý model" window.
 */
@SuppressLint("ViewConstructor")
class ModelsPanel(
    context: Context,
    private val onDownload: (ModelRow) -> Unit,
    private val onUse: (ModelRow) -> Unit,
    private val onDelete: (ModelRow) -> Unit,
    private val onClose: () -> Unit,
) : LinearLayout(context) {
    private val idle = Color.argb(45, 255, 255, 255)
    private val blue = Color.rgb(37, 99, 235)
    private val list = LinearLayout(context).apply { orientation = VERTICAL }
    private val note = TextView(context).apply {
        textSize = 12f; setTextColor(Color.rgb(160, 160, 170)); setPadding(0, context.dp(4), 0, context.dp(6))
    }

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply { setColor(Color.argb(245, 22, 22, 28)); cornerRadius = context.dp(16).toFloat() }
        val pad = context.dp(12)
        setPadding(pad, pad, pad, pad)
        addView(TextView(context).apply { text = "🧠  Model dịch trên máy"; textSize = 16f; setTextColor(Color.WHITE) })
        addView(note)
        addView(ScrollView(context).apply { addView(list) }, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
        addView(Button(context).apply {
            text = "Đóng"; isAllCaps = false; setTextColor(Color.WHITE); setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener { onClose() }
        })
    }

    /** [busy]: the model being downloaded (its buttons and the others are disabled), [message] under the title. */
    fun render(rows: List<ModelRow>, busy: String?, message: String) {
        note.text = message
        list.removeAllViews()
        for (r in rows) {
            val status = when (r.status) {
                "installed" -> "Đã tải"
                "bundled" -> "Có sẵn trong app"
                "update" -> "Có bản mới (${mb(r.download)})"
                else -> "Chưa tải (${mb(r.download)})"
            }
            list.addView(LinearLayout(context).apply {
                orientation = VERTICAL
                background = GradientDrawable().apply { setColor(idle); cornerRadius = context.dp(9).toFloat() }
                setPadding(context.dp(10), context.dp(8), context.dp(10), context.dp(8))
                addView(TextView(context).apply {
                    text = r.label + if (r.active) "  ✓ đang dùng" else ""
                    textSize = 14f; setTextColor(Color.WHITE); typeface = if (r.active) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                })
                addView(TextView(context).apply {
                    text = status + (r.version?.let { " · bản $it" } ?: "")
                    textSize = 12f; setTextColor(Color.rgb(180, 180, 190))
                })
                addView(LinearLayout(context).apply {
                    orientation = HORIZONTAL
                    gravity = Gravity.END
                    val free = busy == null
                    if (r.status == "missing" || r.status == "update") {
                        addView(action(if (r.status == "update") "Cập nhật" else "Tải về", free) { onDownload(r) })
                    }
                    if (!r.active) addView(action("Dùng", free) { onUse(r) })
                    if (r.deletable && !r.active) addView(action("Xóa", free) { onDelete(r) })
                })
            }, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply { setMargins(0, context.dp(4), 0, context.dp(4)) })
        }
    }

    private fun mb(bytes: Long) = "${bytes / 1_000_000} MB"

    private fun action(label: String, enabled: Boolean, run: () -> Unit) = TextView(context).apply {
        text = label
        textSize = 13f
        setTextColor(Color.WHITE)
        setPadding(context.dp(12), context.dp(6), context.dp(12), context.dp(6))
        background = GradientDrawable().apply { setColor(blue); cornerRadius = context.dp(7).toFloat() }
        isEnabled = enabled
        alpha = if (enabled) 1f else 0.4f
        layoutParams = LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply { setMargins(context.dp(6), context.dp(4), 0, 0) }
        setOnClickListener { if (isEnabled) run() }
    }
}
