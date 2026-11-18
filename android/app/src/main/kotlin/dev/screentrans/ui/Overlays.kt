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
    ).apply { gravity = Gravity.TOP or Gravity.START }

    fun add(view: View, p: WindowManager.LayoutParams) = wm.addView(view, p)
    fun update(view: View, p: WindowManager.LayoutParams) = wm.updateViewLayout(view, p)
    fun remove(view: View?) {
        if (view?.isAttachedToWindow == true) wm.removeView(view)
    }
}

fun Context.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

/** Draggable round button; a tap (little movement) calls [onTap]; snaps to the nearest side on release. */
@SuppressLint("ViewConstructor")
class Bubble(context: Context, private val onTap: () -> Unit, private val onMoved: (Int, Int) -> Unit) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(37, 99, 235) }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; textAlign = Paint.Align.CENTER; textSize = context.dp(22).toFloat(); isFakeBoldText = true
    }
    var params: WindowManager.LayoutParams? = null
    private var downX = 0f
    private var downY = 0f
    private var startX = 0
    private var startY = 0
    private var dragging = false

    override fun onDraw(canvas: Canvas) {
        val r = width / 2f
        paint.alpha = 220
        canvas.drawCircle(r, r, r, paint)
        canvas.drawText("T", r, r - (text.descent() + text.ascent()) / 2, text)
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
                    val screenW = resources.displayMetrics.widthPixels
                    p.x = if (p.x + width / 2 < screenW / 2) 0 else screenW - width  // stick to the nearest side
                    context.getSystemService(WindowManager::class.java).updateViewLayout(this, p)
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

/** Full-screen layer to drag the translation region; returns it as a RelRect (or null on cancel). */
@SuppressLint("ViewConstructor")
class RegionSelectView(
    context: Context,
    private val screenW: Int,
    private val screenH: Int,
    private val onDone: (RelRect?) -> Unit,
) : FrameLayout(context) {
    private val dim = Paint().apply { color = Color.argb(77, 0, 0, 0) }
    private val clear = Paint().apply { xfermode = android.graphics.PorterDuffXfermode(android.graphics.PorterDuff.Mode.CLEAR) }
    private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(80, 160, 255); style = Paint.Style.STROKE; strokeWidth = context.dp(2).toFloat()
    }
    private var x0 = -1f
    private var y0 = -1f
    private var x1 = -1f
    private var y1 = -1f
    private val sx = IntArray(2)

    init {
        setWillNotDraw(false)
        setLayerType(LAYER_TYPE_HARDWARE, null)
        val hint = TextView(context).apply {
            text = "Kéo để chọn khung thoại"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(200, 20, 20, 24))
            setPadding(context.dp(12), context.dp(6), context.dp(12), context.dp(6))
        }
        addView(hint, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply {
            topMargin = context.dp(48)
        })
        val buttons = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(Button(context).apply { text = "Huỷ"; setOnClickListener { onDone(null) } })
            addView(Button(context).apply {
                text = "Xong"
                setOnClickListener {
                    if (x0 < 0) onDone(null)
                    else {
                        getLocationOnScreen(sx)  // view coords -> screen coords
                        val r = RelRect.fromPx(
                            (x0 + sx[0]).toInt(), (y0 + sx[1]).toInt(), (x1 + sx[0]).toInt(), (y1 + sx[1]).toInt(), screenW, screenH,
                        )
                        onDone(if (r.isUsable(screenW, screenH)) r else null)
                    }
                }
            })
        }
        addView(buttons, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply {
            bottomMargin = context.dp(64)
        })
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), dim)
        if (x0 >= 0) {
            val r = RectF(minOf(x0, x1), minOf(y0, y1), maxOf(x0, x1), maxOf(y0, y1))
            canvas.drawRect(r, clear)
            canvas.drawRect(r, border)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { x0 = e.x; y0 = e.y; x1 = e.x; y1 = e.y }
            MotionEvent.ACTION_MOVE, MotionEvent.ACTION_UP -> { x1 = e.x; y1 = e.y }
        }
        invalidate()
        return true
    }
}
