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
import dev.screentrans.core.live.BlockStyle
import dev.screentrans.ui.dp
import screentrans.text.Kind
import android.text.Layout as TextLayout

/**
 * Live: the translation of each tracked text block drawn over it (screen coordinates, click-through).
 * Font size follows the source text; colours are sampled from the game ("match") or white on dark.
 * Android caps the opacity of click-through overlays at 0.8 whatever we draw.
 */
@SuppressLint("ViewConstructor")
class LiveAreaLayer(context: Context) : View(context) {
    private class Block(val kind: Kind, val text: String, val rect: RectF, val layout: StaticLayout?, val name: TextPaint?, val bg: Paint)

    private val blocks = LinkedHashMap<String, Block>()
    private val basePx = context.dp(16).toFloat()
    private val minPx = context.dp(9).toFloat()
    private val pad = context.dp(3).toFloat()
    private val onScreen = IntArray(2)

    /** [box] = l, t, r, b in screen pixels; [fontPx] = the source text size (null: default size). */
    fun set(key: String, text: String, box: FloatArray, kind: Kind, fontPx: Float? = null, style: BlockStyle? = null) {
        val rect = RectF(box[0], box[1], box[2], box[3])
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = style?.bgArgb ?: Color.argb(204, 20, 20, 24) }
        val fg = style?.textArgb ?: if (kind == Kind.NAME) Color.rgb(255, 220, 140) else Color.WHITE
        val base = (fontPx ?: basePx).coerceAtLeast(minPx)
        if (kind == Kind.NAME) {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = fg; textSize = base; isFakeBoldText = true }
            blocks[key] = Block(kind, text, rect, null, p, bg)
        } else {
            val w = maxOf(1, (rect.width() - 2 * pad).toInt())
            val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
                color = fg
                // same size as the source; shrinks only when 1.5x the box height is not enough
                textSize = maxOf(minPx, Layout.fitTextPx(text.length, rect.width().toInt(), rect.height().toInt(), base))
            }
            val layout = StaticLayout.Builder.obtain(text, 0, text.length, paint, w)
                .setAlignment(TextLayout.Alignment.ALIGN_NORMAL)
                .setMaxLines(maxOf(1, ((rect.height() * 1.5f) / (paint.textSize * 1.25f)).toInt()))
                .setEllipsize(android.text.TextUtils.TruncateAt.END)
                .build()
            rect.bottom = maxOf(rect.bottom, rect.top + layout.height + 2 * pad)
            blocks[key] = Block(kind, text, rect, layout, null, bg)
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
            canvas.drawRoundRect(b.rect, pad, pad, b.bg)
            val layout = b.layout
            if (layout == null) {
                val p = b.name ?: continue
                canvas.drawText(b.text, b.rect.left + pad, b.rect.bottom - p.descent(), p)
                continue
            }
            canvas.save()
            canvas.translate(b.rect.left + pad, b.rect.top + pad)
            layout.draw(canvas)
            canvas.restore()
        }
        canvas.restore()
    }
}
