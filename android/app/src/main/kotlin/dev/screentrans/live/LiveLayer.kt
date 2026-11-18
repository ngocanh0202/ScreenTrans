package dev.screentrans.live

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.text.StaticLayout
import android.text.TextPaint
import android.util.TypedValue
import android.view.View
import android.widget.TextView
import dev.screentrans.core.Layout
import dev.screentrans.ui.dp
import screentrans.text.Kind
import screentrans.text.Segment
import android.text.Layout as TextLayout

/** Dialogue Live: one translation card per region, placed outside the region (FLAG_NOT_TOUCHABLE). */
@SuppressLint("ViewConstructor")
class LiveCard(context: Context) : TextView(context) {
    init {
        setTextColor(Color.WHITE)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
        setBackgroundColor(Color.argb(217, 20, 20, 24))
        val p = context.dp(10)
        setPadding(p, p / 2, p, p / 2)
    }

    fun show(segments: List<Segment>) {
        text = segments.joinToString("\n") { if (it.kind == Kind.NAME) "[${it.source}]" else it.translation ?: "" }
    }
}

/** Large-area Live: the translation of each tracked block drawn over it (screen coordinates). */
@SuppressLint("ViewConstructor")
class LiveAreaLayer(context: Context) : View(context) {
    private class Block(val segment: Segment, val rect: RectF, val layout: StaticLayout?)

    private val blocks = LinkedHashMap<String, Block>()
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(217, 20, 20, 24) }
    private val namePaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 220, 140); textSize = Layout.MIN_TEXT_PX; isFakeBoldText = true
    }
    private val basePx = context.dp(16).toFloat()
    private val pad = context.dp(4).toFloat()
    private val onScreen = IntArray(2)

    fun set(key: String, seg: Segment) {
        val rect = RectF(seg.left, seg.top, seg.right, seg.bottom)
        if (seg.kind == Kind.NAME) {
            blocks[key] = Block(seg, rect, null)
        } else {
            val text = seg.translation ?: "…"
            val w = maxOf(1, (rect.width() - 2 * pad).toInt())
            val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.WHITE
                textSize = Layout.fitTextPx(text.length, rect.width().toInt(), rect.height().toInt(), basePx)
            }
            val layout = StaticLayout.Builder.obtain(text, 0, text.length, paint, w)
                .setAlignment(TextLayout.Alignment.ALIGN_NORMAL)
                .setMaxLines(maxOf(1, ((rect.height() * 1.5f) / (paint.textSize * 1.25f)).toInt()))
                .setEllipsize(android.text.TextUtils.TruncateAt.END)
                .build()
            rect.bottom = maxOf(rect.bottom, rect.top + layout.height + 2 * pad)
            blocks[key] = Block(seg, rect, layout)
        }
        invalidate()
    }

    fun remove(key: String) {
        if (blocks.remove(key) != null) invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        getLocationOnScreen(onScreen)
        canvas.save()
        canvas.translate(-onScreen[0].toFloat(), -onScreen[1].toFloat())
        for (b in blocks.values) {
            val layout = b.layout
            if (layout == null) {
                canvas.drawText(b.segment.source, b.rect.left, b.rect.bottom - namePaint.descent(), namePaint)
                continue
            }
            canvas.drawRoundRect(b.rect, pad, pad, bg)
            canvas.save()
            canvas.translate(b.rect.left + pad, b.rect.top + pad)
            layout.draw(canvas)
            canvas.restore()
        }
        canvas.restore()
    }
}
