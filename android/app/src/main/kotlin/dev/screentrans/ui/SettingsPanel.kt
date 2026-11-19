package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

/** What the settings panel shows and changes. */
data class SettingsValues(val readable: Boolean, val textScale: Float, val growLong: Boolean, val game: String)

/**
 * "⚙ Cài đặt": translation style [Dễ đọc | Giống game], text size [− 100% +], long translations
 * [Kéo dài khung | Thu nhỏ chữ], then a grid of tools (ignore regions, game, capture check, log).
 * Changes are applied at once through the callbacks; the controller calls [render] with the new values.
 */
@SuppressLint("ViewConstructor")
class SettingsPanel(
    context: Context,
    private var values: SettingsValues,
    private val onReadable: (Boolean) -> Unit,
    private val onScale: (up: Boolean) -> Unit,
    private val onGrowLong: (Boolean) -> Unit,
    tools: List<PanelTile>,
    private val onClose: () -> Unit,
) : LinearLayout(context) {
    private val blue = Color.rgb(37, 99, 235)
    private val idle = Color.argb(45, 255, 255, 255)
    private val readable = segment("Dễ đọc") { onReadable(true) }
    private val likeGame = segment("Giống game") { onReadable(false) }
    private val grow = segment("Kéo dài khung") { onGrowLong(true) }
    private val shrink = segment("Thu nhỏ chữ") { onGrowLong(false) }
    private val scaleLabel = TextView(context).apply {
        gravity = Gravity.CENTER; textSize = 15f; setTextColor(Color.WHITE)
    }

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply { setColor(Color.argb(245, 22, 22, 28)); cornerRadius = context.dp(16).toFloat() }
        val pad = context.dp(12)
        setPadding(pad, pad, pad, pad)
        minimumWidth = context.dp(280)
        addView(title("⚙  Cài đặt"))
        addView(caption("Kiểu bản dịch"))
        addView(pair(readable, likeGame))
        addView(caption("Cỡ chữ bản dịch"))
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(square("−") { onScale(false) })
            addView(scaleLabel, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
            addView(square("+") { onScale(true) })
        })
        addView(caption("Khi bản dịch dài"))
        addView(pair(grow, shrink))
        addView(caption("Bộ OCR"))
        // Only the engines this platform can run: Android has ML Kit (on the phone). Phase 5/7 add more here.
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            val mlkit = segment("ML Kit (trên máy)") {}
            select(mlkit, true)
            addView(mlkit, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        })
        addView(caption("Công cụ"))
        tools.chunked(2).forEach { chunk ->
            addView(LinearLayout(context).apply {
                orientation = HORIZONTAL
                chunk.forEach { t -> addView(tool(t), LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply { setMargins(context.dp(3), context.dp(3), context.dp(3), context.dp(3)) }) }
                if (chunk.size == 1) addView(View(context), LayoutParams(0, 0, 1f))
            })
        }
        addView(TextView(context).apply {
            text = "Đóng"
            gravity = Gravity.CENTER
            textSize = 14f
            setTextColor(Color.rgb(180, 180, 190))
            setPadding(0, context.dp(10), 0, context.dp(2))
            setOnClickListener { onClose() }
        }, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        render(values)
    }

    fun render(v: SettingsValues) {
        values = v
        select(readable, v.readable)
        select(likeGame, !v.readable)
        select(grow, v.growLong)
        select(shrink, !v.growLong)
        scaleLabel.text = "${(v.textScale * 100).toInt()}%"
    }

    private fun title(t: String) = TextView(context).apply {
        text = t; textSize = 16f; setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD
        setPadding(context.dp(4), 0, 0, context.dp(4))
    }

    private fun caption(t: String) = TextView(context).apply {
        text = t; textSize = 12f; setTextColor(Color.rgb(160, 160, 170))
        setPadding(context.dp(4), context.dp(10), 0, context.dp(4))
    }

    private fun pair(a: View, b: View) = LinearLayout(context).apply {
        orientation = HORIZONTAL
        background = GradientDrawable().apply { setColor(idle); cornerRadius = context.dp(9).toFloat() }
        setPadding(context.dp(3), context.dp(3), context.dp(3), context.dp(3))
        addView(a, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        addView(b, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
    }

    private fun segment(label: String, action: () -> Unit) = TextView(context).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 14f
        setPadding(context.dp(8), context.dp(9), context.dp(8), context.dp(9))
        background = GradientDrawable().apply { cornerRadius = context.dp(7).toFloat() }
        setOnClickListener { action() }
    }

    private fun select(v: TextView, on: Boolean) {
        (v.background as GradientDrawable).setColor(if (on) blue else Color.TRANSPARENT)
        v.setTextColor(if (on) Color.WHITE else Color.rgb(190, 190, 200))
        v.typeface = if (on) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
    }

    private fun square(label: String, action: () -> Unit) = TextView(context).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 20f
        setTextColor(Color.WHITE)
        background = GradientDrawable().apply { setColor(idle); cornerRadius = context.dp(9).toFloat() }
        layoutParams = LayoutParams(context.dp(48), context.dp(44))
        setOnClickListener { action() }
    }

    private fun tool(t: PanelTile) = LinearLayout(context).apply {
        orientation = VERTICAL
        gravity = Gravity.CENTER
        minimumHeight = context.dp(64)
        setPadding(context.dp(4), context.dp(6), context.dp(4), context.dp(6))
        background = GradientDrawable().apply { setColor(idle); cornerRadius = context.dp(12).toFloat() }
        addView(TextView(context).apply { text = t.icon; gravity = Gravity.CENTER; textSize = 18f; setTextColor(Color.WHITE) })
        addView(TextView(context).apply { text = t.label; gravity = Gravity.CENTER; textSize = 11f; setTextColor(Color.WHITE); maxLines = 2 })
        setOnClickListener { onClose(); t.action() }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (e.actionMasked == MotionEvent.ACTION_OUTSIDE) {
            onClose()
            return true
        }
        return super.onTouchEvent(e)
    }
}
