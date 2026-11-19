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
import dev.screentrans.core.llm.DEFAULT_MODELS
import dev.screentrans.core.llm.NAMES

/** What "Dịch bằng" shows: the game's engine and notes, the app-wide remote settings. */
data class LlmValues(
    val game: String,
    val engine: String,
    val savedKeys: Set<String>,
    val models: Map<String, String>,
    val kaggleUrl: String,
    val dailyLimit: Int,
    val usedToday: Int,
    val notes: String,
)

/** What the user saved: [key] only when typed (null = unchanged), [deleteKey] for the shown engine. */
data class LlmEdit(
    val engine: String,
    val key: String?,
    val deleteKey: Boolean,
    val model: String,
    val kaggleUrl: String,
    val dailyLimit: Int,
    val notes: String,
)

/**
 * "🌐 Dịch bằng" (Phase 5): the game's translation engine [Máy | Gemini | OpenAI | Claude | Kaggle], key (a saved
 * key is never shown), model name, Kaggle URL, daily limit, characters used today, privacy warning, game notes.
 * A focusable overlay (keyboard) that scrolls. Same fields as the Windows settings window.
 */
@SuppressLint("ViewConstructor")
class LlmPanel(
    context: Context,
    private val v: LlmValues,
    private val onSave: (LlmEdit) -> Unit,
    private val onClose: () -> Unit,
) : LinearLayout(context) {
    private val blue = Color.rgb(37, 99, 235)
    private val idle = Color.argb(45, 255, 255, 255)
    private val engines = listOf("local" to "Máy", "gemini" to "Gemini", "openai" to "OpenAI", "claude" to "Claude", "kaggle" to "Kaggle")
    private var engine = v.engine
    private var deleteKey = false
    private val segments = engines.associate { (id, label) -> id to segment(label) { pick(id) } }
    private val key = field("Dán key / token vào đây", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
    private val deleteButton = button("Xóa key") { deleteKey = true; key.setText(""); show() }
    private val model = field("Tên model", InputType.TYPE_CLASS_TEXT)
    private val url = field("https://….ngrok-free.app", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI)
    private val limit = field("Ký tự mỗi ngày", InputType.TYPE_CLASS_NUMBER).apply { setText(v.dailyLimit.toString()) }
    private val privacy = TextView(context).apply { textSize = 12f; setTextColor(Color.rgb(250, 190, 90)) }
    private val notes = field("Bối cảnh, nhân vật, cách xưng hô (vd: Vertin: nữ, gọi Sonetto là \"em\")",
        InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE).apply { setText(v.notes); minLines = 2 }
    private val remoteRows = mutableListOf<android.view.View>()
    private var urlRow: android.view.View? = null

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply { setColor(Color.argb(245, 22, 22, 28)); cornerRadius = context.dp(16).toFloat() }
        val pad = context.dp(12)
        setPadding(pad, pad, pad, pad)
        val body = LinearLayout(context).apply { orientation = VERTICAL }
        body.addView(TextView(context).apply { text = "🌐  Dịch bằng — ${v.game}"; textSize = 16f; setTextColor(Color.WHITE) })
        val grid = FlowLayout(context)
        segments.values.forEach { grid.addView(it) }
        body.addView(grid)
        fun row(label: String, view: android.view.View, remote: Boolean = true): android.view.View {
            val r = LinearLayout(context).apply {
                orientation = VERTICAL
                addView(caption(label))
                addView(view)
            }
            body.addView(r)
            if (remote) remoteRows.add(r)
            return r
        }
        row("Key / token", LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(key, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
            addView(deleteButton)
        })
        row("Tên model", model)
        urlRow = row("URL server Kaggle", url)
        row("Giới hạn mỗi ngày (đã dùng hôm nay: ${v.usedToday} ký tự)", limit)
        body.addView(privacy)
        remoteRows.add(privacy)
        row("Ghi chú game cho LLM", notes)
        addView(ScrollView(context).apply { addView(body) }, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            addView(button("Hủy") { onClose() })
            addView(button("Lưu") { onSave(edit()) })
        })
        pick(engine)
    }

    private fun pick(id: String) {
        if (engine != id) {
            key.setText("")
            deleteKey = false
        }
        engine = id
        model.setText(v.models[id] ?: DEFAULT_MODELS[id] ?: "")
        url.setText(v.kaggleUrl)
        show()
    }

    private fun show() {
        segments.forEach { (id, s) -> (s.background as GradientDrawable).setColor(if (id == engine) blue else idle) }
        val remote = engine in NAMES
        remoteRows.forEach { it.visibility = if (remote) VISIBLE else GONE }
        urlRow?.visibility = if (engine == "kaggle") VISIBLE else GONE
        val saved = engine in v.savedKeys && !deleteKey
        key.hint = if (saved) "•••• (đã lưu — nhập để thay)" else "Dán key / token vào đây"
        deleteButton.isEnabled = saved
        deleteButton.alpha = if (saved) 1f else 0.4f
        privacy.text = if (remote) "Chữ trong game sẽ được gửi tới ${NAMES[engine]} để dịch (tính phí theo tài khoản của bạn). " +
            "Lỗi / hết hạn mức → tự dùng model trên máy." else ""
    }

    private fun edit() = LlmEdit(
        engine = engine,
        key = key.text.toString().takeIf { it.isNotBlank() },
        deleteKey = deleteKey,
        model = model.text.toString().trim(),
        kaggleUrl = url.text.toString().trim(),
        dailyLimit = limit.text.toString().toIntOrNull()?.coerceAtLeast(1000) ?: v.dailyLimit,
        notes = notes.text.toString().trim(),
    )

    private fun field(hint: String, type: Int) = EditText(context).apply {
        this.hint = hint
        setHintTextColor(Color.GRAY)
        setTextColor(Color.WHITE)
        inputType = type
    }

    private fun segment(label: String, action: () -> Unit) = TextView(context).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 14f
        setTextColor(Color.WHITE)
        setPadding(context.dp(10), context.dp(8), context.dp(10), context.dp(8))
        background = GradientDrawable().apply { cornerRadius = context.dp(7).toFloat() }
        setOnClickListener { action() }
    }

    private fun caption(t: String) = TextView(context).apply {
        text = t; textSize = 12f; setTextColor(Color.rgb(160, 160, 170)); setPadding(0, context.dp(8), 0, context.dp(2))
    }

    private fun button(label: String, action: () -> Unit) = Button(context).apply {
        text = label
        isAllCaps = false
        setTextColor(Color.WHITE)
        setBackgroundColor(Color.TRANSPARENT)
        setOnClickListener { action() }
    }
}
