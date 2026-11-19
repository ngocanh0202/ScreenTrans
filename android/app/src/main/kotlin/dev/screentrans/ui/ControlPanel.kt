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

/** One extra tile: icon, label, action. */
data class PanelTile(val icon: String, val label: String, val action: () -> Unit)

/**
 * The bubble's panel as a grid of tiles:
 *   [① Dịch 1 lần | ∞ Tự động]   [▭ Vùng | ⛶ Toàn màn hình]   [✎ Chọn vùng | ▶ main button]
 * and "Thêm ▾" opening a 3-column grid of the less used items. Touching outside closes it.
 * Rules (what is enabled, what the main tile does) live in [PanelState].
 */
@SuppressLint("ViewConstructor")
class ControlPanel(
    context: Context,
    private var state: PanelState,
    private val onMode: (TranslateMode) -> Unit,
    private val onScope: (Boolean) -> Unit,
    private val onChooseRegion: () -> Unit,
    private val onPrimary: (PanelAction) -> Unit,
    extras: List<PanelTile>,
    private val onClose: () -> Unit,
) : LinearLayout(context) {
    private val blue = Color.rgb(37, 99, 235)
    private val green = Color.rgb(22, 163, 74)
    private val red = Color.rgb(220, 38, 38)
    private val idle = Color.argb(45, 255, 255, 255)
    private val modeOnce = tile("①", "Dịch 1 lần") { onMode(TranslateMode.ONCE) }
    private val modeLive = tile("∞", "Tự động") { onMode(TranslateMode.LIVE) }
    private val scopeRegion = tile("▭", "Vùng") { onScope(false) }
    private val scopeScreen = tile("⛶", "Toàn màn hình") { onScope(true) }
    private val chooseRegion = tile("✎", "Chọn vùng") { onChooseRegion() }
    private val primary = tile("▶", "") { onPrimary(state.primary.first) }
    private val more = TextView(context)
    private val extraGrid = LinearLayout(context).apply { orientation = VERTICAL; visibility = GONE }

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply { setColor(Color.argb(240, 22, 22, 28)); cornerRadius = context.dp(16).toFloat() }
        val pad = context.dp(8)
        setPadding(pad, pad, pad, pad)
        addView(row(listOf(modeOnce, modeLive)))
        addView(row(listOf(scopeRegion, scopeScreen)))
        addView(row(listOf(chooseRegion, primary)))
        more.apply {
            text = "Thêm ▾"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(170, 170, 180))
            textSize = 13f
            setPadding(0, context.dp(6), 0, context.dp(4))
            setOnClickListener {
                val open = extraGrid.visibility != VISIBLE
                extraGrid.visibility = if (open) VISIBLE else GONE
                text = if (open) "Thêm ▴" else "Thêm ▾"
            }
        }
        addView(more, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        extras.chunked(3).forEach { chunk ->
            val tiles = chunk.map { t -> tile(t.icon, t.label, small = true) { onClose(); t.action() }.also { paint(it, idle, true) } }
            extraGrid.addView(row(tiles, columns = 3))
        }
        addView(extraGrid)
        render(state)
    }

    /** Redraw after a toggle changed (the controller passes the new state). */
    fun render(s: PanelState) {
        state = s
        paint(modeOnce, if (s.mode == TranslateMode.ONCE) blue else idle, s.mode == TranslateMode.ONCE)
        paint(modeLive, if (s.mode == TranslateMode.LIVE) blue else idle, s.mode == TranslateMode.LIVE)
        paint(scopeRegion, if (!s.screen) blue else idle, !s.screen)
        paint(scopeScreen, if (s.screen) blue else idle, s.screen)
        paint(chooseRegion, idle, false)
        chooseRegion.isEnabled = s.chooseRegionEnabled
        chooseRegion.alpha = if (s.chooseRegionEnabled) 1f else 0.3f
        val (action, label) = s.primary
        (primary.getChildAt(0) as TextView).text = if (action == PanelAction.STOP_LIVE) "■" else "▶"
        (primary.getChildAt(1) as TextView).text = label
        paint(primary, when (action) {
            PanelAction.START_LIVE -> green
            PanelAction.STOP_LIVE -> red
            else -> blue
        }, true)
    }

    private fun row(tiles: List<View>, columns: Int = 2) = LinearLayout(context).apply {
        orientation = HORIZONTAL
        tiles.forEach { addView(it, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply { setMargins(context.dp(3), context.dp(3), context.dp(3), context.dp(3)) }) }
        repeat(columns - tiles.size) { addView(View(context), LayoutParams(0, 0, 1f).apply { setMargins(context.dp(3), 0, context.dp(3), 0) }) }
    }

    /** A square-ish tile: a big icon above a short label. */
    private fun tile(icon: String, label: String, small: Boolean = false, action: () -> Unit) = LinearLayout(context).apply {
        orientation = VERTICAL
        gravity = Gravity.CENTER
        val size = context.dp(if (small) 74 else 96)
        minimumWidth = size
        minimumHeight = context.dp(if (small) 64 else 76)
        setPadding(context.dp(4), context.dp(6), context.dp(4), context.dp(6))
        background = GradientDrawable().apply { cornerRadius = context.dp(12).toFloat() }
        addView(TextView(context).apply {
            text = icon
            gravity = Gravity.CENTER
            textSize = if (small) 18f else 24f
            setTextColor(Color.WHITE)
        })
        addView(TextView(context).apply {
            text = label
            gravity = Gravity.CENTER
            textSize = if (small) 11f else 13f
            setTextColor(Color.WHITE)
            maxLines = 2
        })
        setOnClickListener { action() }
    }

    private fun paint(tile: LinearLayout, color: Int, strong: Boolean) {
        (tile.background as GradientDrawable).setColor(color)
        (tile.getChildAt(1) as TextView).apply {
            setTextColor(if (strong) Color.WHITE else Color.rgb(200, 200, 210))
            typeface = if (strong) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
        }
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
