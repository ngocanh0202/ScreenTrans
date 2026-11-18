package dev.screentrans.live

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.text.StaticLayout
import android.text.TextPaint
import android.view.View
import dev.screentrans.core.Layout
import dev.screentrans.ui.dp
import screentrans.text.Kind
import screentrans.text.Segment
import android.text.Layout as TextLayout

/** Live: the translation of each tracked text block drawn over it (screen coordinates, click-through). */
@SuppressLint("ViewConstructor")
class LiveAreaLayer(context: Context) : View(context) {
    private class Block(val segment: Segment, val rect: RectF, val layout: StaticLayout?)

    private val blocks = LinkedHashMap<String, Block>()
    // click-through overlays: Android caps their opacity at 0.8
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(204, 20, 20, 24) }
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

    /** [box] = l, t, r, b in screen pixels. */
    fun set(key: String, text: String, box: FloatArray, kind: Kind) =
        set(key, Segment(kind, text, if (kind == Kind.NAME) null else text, box[0], box[1], box[2], box[3]))

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
