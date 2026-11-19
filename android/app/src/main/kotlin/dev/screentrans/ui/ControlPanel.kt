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
import dev.screentrans.core.ui.PanelAction
import dev.screentrans.core.ui.PanelState
import dev.screentrans.core.ui.TranslateMode

/**
 * The bubble's panel: [Dịch 1 lần | Tự động dịch], [Vùng | Toàn màn hình], "Chọn vùng…" (only for
 * Vùng), one main button that follows the two toggles, and "Thêm ▾" with the less used items.
 * Touching outside closes it. Rules (what is enabled, what the button does) live in [PanelState].
 */
@SuppressLint("ViewConstructor")
class ControlPanel(
    context: Context,
    private var state: PanelState,
    private val onMode: (TranslateMode) -> Unit,
    private val onScope: (Boolean) -> Unit,
    private val onChooseRegion: () -> Unit,
    private val onPrimary: (PanelAction) -> Unit,
    private val extras: List<Pair<String, () -> Unit>>,
    private val onClose: () -> Unit,
) : LinearLayout(context) {
    private val blue = Color.rgb(37, 99, 235)
    private val green = Color.rgb(22, 163, 74)
    private val red = Color.rgb(220, 38, 38)
    private val modeOnce = segment("Dịch 1 lần") { onMode(TranslateMode.ONCE) }
    private val modeLive = segment("Tự động dịch") { onMode(TranslateMode.LIVE) }
    private val scopeRegion = segment("Vùng") { onScope(false) }
    private val scopeScreen = segment("Toàn màn hình") { onScope(true) }
    private val chooseRegion = button("Chọn vùng…", Color.argb(50, 255, 255, 255)) { onChooseRegion() }
    private val primary = button("", blue) { onPrimary(state.primary.first) }
    private val more = TextView(context)
    private val extraBox = LinearLayout(context).apply { orientation = VERTICAL; visibility = GONE }

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply { setColor(Color.argb(240, 22, 22, 28)); cornerRadius = context.dp(14).toFloat() }
        val pad = context.dp(10)
        setPadding(pad, pad, pad, pad)
        minimumWidth = context.dp(230)
        addView(pair(modeOnce, modeLive))
        addView(pair(scopeRegion, scopeScreen), gap())
        addView(chooseRegion, gap())
        addView(primary, gap())
        more.apply {
            text = "Thêm ▾"
            setTextColor(Color.rgb(170, 170, 180))
            textSize = 13f
            setPadding(context.dp(4), context.dp(10), context.dp(4), context.dp(2))
            setOnClickListener {
                val open = extraBox.visibility != VISIBLE
                extraBox.visibility = if (open) VISIBLE else GONE
                text = if (open) "Thêm ▴" else "Thêm ▾"
            }
        }
        addView(more)
        for ((label, action) in extras) {
            extraBox.addView(TextView(context).apply {
                text = label
                setTextColor(Color.WHITE)
                textSize = 14f
                setPadding(context.dp(6), context.dp(9), context.dp(6), context.dp(9))
                setOnClickListener { onClose(); action() }
            })
        }
        addView(extraBox)
        render(state)
    }

    /** Redraw after a toggle changed (the controller passes the new state). */
    fun render(s: PanelState) {
        state = s
        select(modeOnce, s.mode == TranslateMode.ONCE)
        select(modeLive, s.mode == TranslateMode.LIVE)
        select(scopeRegion, !s.screen)
        select(scopeScreen, s.screen)
        chooseRegion.isEnabled = s.chooseRegionEnabled
        chooseRegion.alpha = if (s.chooseRegionEnabled) 1f else 0.35f
        val (action, label) = s.primary
        primary.text = (if (action == PanelAction.STOP_LIVE) "■  " else "▶  ") + label
        (primary.background as GradientDrawable).setColor(
            when (action) {
                PanelAction.START_LIVE -> green
                PanelAction.STOP_LIVE -> red
                else -> blue
            },
        )
    }

    private fun gap() = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply { topMargin = context.dp(8) }

    private fun pair(a: View, b: View) = LinearLayout(context).apply {
        orientation = HORIZONTAL
        background = GradientDrawable().apply { setColor(Color.argb(40, 255, 255, 255)); cornerRadius = context.dp(9).toFloat() }
        setPadding(context.dp(3), context.dp(3), context.dp(3), context.dp(3))
        addView(a, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        addView(b, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
    }

    private fun segment(label: String, action: () -> Unit) = TextView(context).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 14f
        setPadding(context.dp(10), context.dp(8), context.dp(10), context.dp(8))
        background = GradientDrawable().apply { cornerRadius = context.dp(7).toFloat() }
        setOnClickListener { action() }
    }

    private fun select(v: TextView, on: Boolean) {
        (v.background as GradientDrawable).setColor(if (on) blue else Color.TRANSPARENT)
        v.setTextColor(if (on) Color.WHITE else Color.rgb(190, 190, 200))
        v.typeface = if (on) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
    }

    private fun button(label: String, color: Int, action: () -> Unit) = TextView(context).apply {
        text = label
        gravity = Gravity.CENTER
        textSize = 15f
        setTextColor(Color.WHITE)
        setPadding(context.dp(12), context.dp(11), context.dp(12), context.dp(11))
        background = GradientDrawable().apply { setColor(color); cornerRadius = context.dp(9).toFloat() }
        setOnClickListener { action() }
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
