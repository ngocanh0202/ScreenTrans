package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RectF
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.screentrans.core.RelRect
import kotlin.math.abs

/** Adds/removes views as TYPE_APPLICATION_OVERLAY windows. */
class Overlays(private val context: Context) {
    val wm: WindowManager = context.getSystemService(WindowManager::class.java)

    fun params(w: Int, h: Int, focusable: Boolean = false, touchable: Boolean = true) = WindowManager.LayoutParams(
        w, h,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        (if (focusable) 0 else WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE) or
            (if (touchable) 0 else WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE) or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
            WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
        PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.TOP or Gravity.START
        // Android 12+ blocks touches that pass through another app's window more opaque than 0.8:
        // click-through overlays must stay at or below it so the game under them keeps working.
        if (!touchable) alpha = 0.8f
        // Overlays draw in screen coordinates (OCR boxes, regions): never shift them for a display
        // cutout or the system bars.
        layoutInDisplayCutoutMode = if (android.os.Build.VERSION.SDK_INT >= 30)
            WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
        else WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        if (android.os.Build.VERSION.SDK_INT >= 30) setFitInsetsTypes(0)
    }

    fun add(view: View, p: WindowManager.LayoutParams) = wm.addView(view, p)
    fun update(view: View, p: WindowManager.LayoutParams) = wm.updateViewLayout(view, p)
    /** Added views get their parent synchronously in addView; isAttachedToWindow only after the first traversal. */
    fun isAdded(view: View?): Boolean = view?.parent != null

    fun remove(view: View?) {
        if (isAdded(view)) wm.removeView(view)
    }
}

fun Context.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

/**
 * The bubble, tucked into the screen edge: a small tab with an arrow pointing inwards. A tap (little
 * movement) calls [onTap]; it can be dragged and snaps back to the nearest side. Green while Live runs.
 */
@SuppressLint("ViewConstructor")
class Bubble(context: Context, private val onTap: () -> Unit, private val onMoved: (Int, Int) -> Unit) : View(context) {
    companion object {
        const val TAB_W_DP = 22
        const val TAB_H_DP = 58
    }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val arrow = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = context.dp(3).toFloat()
        strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }
    private val path = android.graphics.Path()
    var params: WindowManager.LayoutParams? = null

    /** Live is running: the tab turns green. */
    var live = false
        set(v) {
            if (field != v) { field = v; invalidate() }
        }
    private var downX = 0f
    private var downY = 0f
    private var startX = 0
    private var startY = 0
    private var dragging = false

    private fun onLeftSide(): Boolean = (params?.x ?: 0) + width / 2 < resources.displayMetrics.widthPixels / 2

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        val r = w * 0.9f
        val left = onLeftSide()
        paint.color = if (live) Color.rgb(22, 163, 74) else Color.rgb(37, 99, 235)
        paint.alpha = 200
        // rounded on the screen side away from the edge only
        val rect = RectF(if (left) -r else 0f, 0f, if (left) w else w + r, h)
        canvas.drawRoundRect(rect, r, r, paint)
        val cx = w / 2
        val cy = h / 2
        val a = w * 0.22f
        path.reset()
        if (left) { path.moveTo(cx - a / 2, cy - a); path.lineTo(cx + a / 2, cy); path.lineTo(cx - a / 2, cy + a) }
        else { path.moveTo(cx + a / 2, cy - a); path.lineTo(cx - a / 2, cy); path.lineTo(cx + a / 2, cy + a) }
        canvas.drawPath(path, arrow)
    }

    /** Snap to the nearest side (call after a drag, a rotation or on start). */
    fun snap(p: WindowManager.LayoutParams, screenW: Int, screenH: Int) {
        p.x = if (p.x + p.width / 2 < screenW / 2) 0 else screenW - p.width
        p.y = p.y.coerceIn(0, maxOf(0, screenH - p.height))
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        val p = params ?: return false
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = e.rawX; downY = e.rawY; startX = p.x; startY = p.y; dragging = false
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = e.rawX - downX
                val dy = e.rawY - downY
                if (abs(dx) > context.dp(6) || abs(dy) > context.dp(6)) dragging = true
                if (dragging) {
                    p.x = startX + dx.toInt(); p.y = startY + dy.toInt()
                    context.getSystemService(WindowManager::class.java).updateViewLayout(this, p)
                }
            }
            MotionEvent.ACTION_UP -> {
                if (!dragging) onTap() else {
                    val dm = resources.displayMetrics
                    snap(p, dm.widthPixels, dm.heightPixels)
                    context.getSystemService(WindowManager::class.java).updateViewLayout(this, p)
                    invalidate()  // the arrow may now point the other way
                    onMoved(p.x, p.y)
                }
            }
        }
        return true
    }
}

/** The bubble's menu: Dịch vùng / Toàn màn hình / Chọn vùng mới. Touching outside closes it. */
@SuppressLint("ViewConstructor")
class MenuPanel(context: Context, items: List<Pair<String, () -> Unit>>, private val onClose: () -> Unit) : LinearLayout(context) {
    init {
        orientation = VERTICAL
        setBackgroundColor(Color.argb(235, 20, 20, 24))
        setPadding(context.dp(4), context.dp(4), context.dp(4), context.dp(4))
        for ((label, action) in items) {
            addView(Button(context).apply {
                text = label
                isAllCaps = false
                setTextColor(Color.WHITE)
                setBackgroundColor(Color.TRANSPARENT)
                setOnClickListener { onClose(); action() }
            })
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
