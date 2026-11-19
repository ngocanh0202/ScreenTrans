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
    private class Block(
        val kind: Kind, val text: String, val rect: RectF, val layout: StaticLayout?, val name: TextPaint?, val bg: Paint,
        val angle: Float = 0f,  // tilted text: drawn rotated by angle around the screen origin
    )

    private val blocks = LinkedHashMap<String, Block>()
    private val basePx = context.dp(16).toFloat()
    private val minPx = context.dp(9).toFloat()
    private val pad = context.dp(3).toFloat()
    private val onScreen = IntArray(2)

    /** Translation text size factor (settings "Cỡ chữ"). */
    var scale = 1f

    /** Long translations: extend the box downwards first (true) or only shrink the font (false). */
    var growLong = true

    /**
     * [box] = l, t, r, b in screen pixels; [fontPx] = the source text size (null: default size).
     * The whole translation is drawn: the box may run past the source text (moved up near the screen bottom).
     */
    fun set(key: String, text: String, box: FloatArray, kind: Kind, fontPx: Float? = null, style: BlockStyle? = null,
            angle: Float = 0f) {
        val rect = RectF(box[0], box[1], box[2], box[3])
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = style?.bgArgb ?: Color.argb(204, 20, 20, 24) }
        val fg = style?.textArgb ?: if (kind == Kind.NAME) Color.rgb(255, 220, 140) else Color.WHITE
        val base = ((fontPx ?: basePx) * scale).coerceAtLeast(minPx)
        if (kind == Kind.NAME) {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = fg; textSize = base; isFakeBoldText = true }
            blocks[key] = Block(kind, text, rect, null, p, bg, angle)
        } else {
            val w = maxOf(1, (rect.width() - 2 * pad).toInt())
            val screenH = resources.displayMetrics.heightPixels
            val fit = Layout.fitBlock(text.length, rect.width().toInt(), rect.height().toInt(), base,
                grow = growLong && angle == 0f)
            val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = fg; textSize = maxOf(minPx, fit.px) }
            val layout = StaticLayout.Builder.obtain(text, 0, text.length, paint, w)
                .setAlignment(TextLayout.Alignment.ALIGN_NORMAL)
                .build()
            rect.bottom = maxOf(rect.bottom, rect.top + layout.height + 2 * pad)
            rect.top = Layout.liftedTop(rect.top, paint.textSize, tilted = angle != 0f)
            if (angle == 0f) rect.offsetTo(rect.left, Layout.onScreenTop(rect.top, rect.height().toInt(), screenH))
            blocks[key] = Block(kind, text, rect, layout, null, bg, angle)
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
            canvas.save()
            if (b.angle != 0f) canvas.rotate(b.angle)  // the block is in a frame tilted around the screen origin
            canvas.drawRoundRect(b.rect, pad, pad, b.bg)
            val layout = b.layout
            if (layout == null) {
                b.name?.let { p -> canvas.drawText(b.text, b.rect.left + pad, b.rect.bottom - p.descent(), p) }
            } else {
                canvas.translate(b.rect.left + pad, b.rect.top + pad)
                layout.draw(canvas)
            }
            canvas.restore()
        }
        canvas.restore()
    }
}
