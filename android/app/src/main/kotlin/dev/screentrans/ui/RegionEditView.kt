package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.view.Gravity
import android.view.MotionEvent
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import dev.screentrans.core.RegionEdit
import dev.screentrans.core.RelRect

/**
 * Edit the translation regions: drag on empty space to add one, drag a corner handle to resize,
 * drag inside to move, "Xoá vùng" removes the selected one. Returns the list (null on cancel).
 * All rects are kept in screen pixels while editing.
 */
@SuppressLint("ViewConstructor")
class RegionEditView(
    context: Context,
    private val screenW: Int,
    private val screenH: Int,
    initial: List<RelRect>,
    private val onDone: (List<RelRect>?) -> Unit,
) : FrameLayout(context) {
    private val rects = initial.map { it.toPx(screenW, screenH) }.toMutableList()
    private var selected = rects.lastIndex
    private val handle = context.dp(24)
    private val origin = IntArray(2)

    private val dim = Paint().apply { color = Color.argb(77, 0, 0, 0) }
    private val clear = Paint().apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.CLEAR) }
    private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = context.dp(2).toFloat() }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE; textSize = context.dp(14).toFloat(); isFakeBoldText = true
    }

    // current gesture
    private var hit: RegionEdit.Hit? = null
    private var startRect: IntArray? = null
    private var downX = 0
    private var downY = 0
    private var creating: IntArray? = null

    init {
        setWillNotDraw(false)
        setLayerType(LAYER_TYPE_HARDWARE, null)
        val hint = TextView(context).apply {
            text = "Kéo chỗ trống để thêm vùng · kéo góc để đổi cỡ · kéo giữa để di chuyển"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(200, 20, 20, 24))
            setPadding(context.dp(12), context.dp(6), context.dp(12), context.dp(6))
        }
        addView(hint, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply {
            topMargin = context.dp(40)
        })
        val buttons = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(Button(context).apply {
                text = "Xoá vùng"
                setOnClickListener {
                    if (selected in rects.indices) rects.removeAt(selected)
                    selected = rects.lastIndex
                    invalidate()
                }
            })
            addView(Button(context).apply { text = "Huỷ"; setOnClickListener { onDone(null) } })
            addView(Button(context).apply {
                text = "Xong"
                setOnClickListener {
                    onDone(rects.map { RelRect.fromPx(it[0], it[1], it[2], it[3], screenW, screenH) }
                        .filter { it.isUsable(screenW, screenH) })
                }
            })
        }
        addView(buttons, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply {
            bottomMargin = context.dp(56)
        })
    }

    override fun onDraw(canvas: Canvas) {
        getLocationOnScreen(origin)  // rects are screen coordinates
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), dim)
        canvas.save()
        canvas.translate(-origin[0].toFloat(), -origin[1].toFloat())
        val all = rects + listOfNotNull(creating)
        all.forEachIndexed { i, r ->
            val f = android.graphics.RectF(r[0].toFloat(), r[1].toFloat(), r[2].toFloat(), r[3].toFloat())
            canvas.drawRect(f, clear)
            border.color = if (i == selected) Color.rgb(80, 160, 255) else Color.rgb(200, 200, 200)
            canvas.drawRect(f, border)
            if (i < rects.size) {
                for ((x, y) in listOf(r[0] to r[1], r[2] to r[1], r[0] to r[3], r[2] to r[3])) {
                    canvas.drawCircle(x.toFloat(), y.toFloat(), context.dp(7).toFloat(), dot)
                }
                canvas.drawText("${i + 1}", f.left + context.dp(6), f.top + label.textSize + context.dp(2), label)
            }
        }
        canvas.restore()
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        val x = e.rawX.toInt()
        val y = e.rawY.toInt()
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = x; downY = y
                hit = RegionEdit.hitTest(rects, x, y, handle)
                val h = hit
                if (h != null) {
                    selected = h.index
                    startRect = rects[h.index].copyOf()
                } else {
                    creating = intArrayOf(x, y, x, y)
                }
            }
            MotionEvent.ACTION_MOVE -> {
                val h = hit
                val start = startRect
                if (h != null && start != null) {
                    rects[h.index] = RegionEdit.drag(start, h.part, x - downX, y - downY, screenW, screenH)
                } else {
                    creating = intArrayOf(minOf(downX, x), minOf(downY, y), maxOf(downX, x), maxOf(downY, y))
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val c = creating
                if (c != null && c[2] - c[0] >= RegionEdit.MIN_SIZE && c[3] - c[1] >= RegionEdit.MIN_SIZE) {
                    rects.add(c)
                    selected = rects.lastIndex
                }
                creating = null
                hit = null
                startRect = null
            }
        }
        invalidate()
        return true
    }
}
