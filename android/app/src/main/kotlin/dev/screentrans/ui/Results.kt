package dev.screentrans.ui

import android.annotation.SuppressLint
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.Layout as TextLayout
import android.text.SpannableStringBuilder
import android.text.StaticLayout
import android.text.TextPaint
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import dev.screentrans.core.Layout
import screentrans.text.Kind
import screentrans.text.Segment

/** Dark card with the translation of a region; Copy button; touching outside closes it. */
@SuppressLint("ViewConstructor")
class ResultCard(context: Context, private val onClose: () -> Unit) : LinearLayout(context) {
    private val text = TextView(context).apply {
        setTextColor(Color.WHITE)
        textSize = 16f
        setLineSpacing(0f, 1.15f)
    }
    private val copy = Button(context).apply {
        text = "Copy"
        isAllCaps = false
        setTextColor(Color.WHITE)
        setBackgroundColor(Color.argb(40, 255, 255, 255))
    }
    private var translations: List<String> = emptyList()

    init {
        orientation = VERTICAL
        background = GradientDrawable().apply {
            setColor(Color.argb(217, 20, 20, 24))  // 85%
            cornerRadius = context.dp(10).toFloat()
        }
        setPadding(context.dp(14), context.dp(10), context.dp(14), context.dp(8))
        addView(text)
        addView(copy, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply { topMargin = context.dp(6) })
        copy.setOnClickListener {
            val cm = context.getSystemService(ClipboardManager::class.java)
            cm.setPrimaryClip(ClipData.newPlainText("ScreenTrans", translations.joinToString("\n")))
            copy.text = "Đã copy"
        }
    }

    fun showMessage(message: String, error: Boolean = false) {
        translations = emptyList()
        text.text = message
        text.setTextColor(if (error) Color.rgb(255, 154, 154) else Color.WHITE)
        copy.visibility = GONE
    }

    fun showSegments(segments: List<Segment>, showSource: Boolean = false) {
        val sb = SpannableStringBuilder()
        translations = segments.filter { it.kind == Kind.TEXT }.mapNotNull { it.translation }
        for (s in segments) {
            if (sb.isNotEmpty()) sb.append("\n")
            if (s.kind == Kind.NAME) {
                val start = sb.length
                sb.append("[${s.source}]")
                sb.setSpan(StyleSpan(Typeface.BOLD), start, sb.length, 0)
                continue
            }
            if (showSource) {
                val start = sb.length
                sb.append(s.source).append("\n")
                sb.setSpan(ForegroundColorSpan(Color.rgb(184, 184, 184)), start, sb.length, 0)
            }
            sb.append(s.translation ?: "")
        }
        text.setTextColor(Color.WHITE)
        text.text = if (sb.isEmpty()) "(không tìm thấy chữ)" else sb
        copy.text = "Copy"
        copy.visibility = if (translations.isEmpty()) GONE else VISIBLE
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

/** Full-screen layer: each translated block drawn over its source text; tap a block for details. */
@SuppressLint("ViewConstructor")
class FullScreenLayer(
    context: Context,
    private val onBlockTapped: (Segment) -> Unit,
    private val onClose: () -> Unit,
) : View(context) {
    private class Block(val segment: Segment, val rect: RectF, val layout: StaticLayout?)

    private val blocks = mutableListOf<Block>()
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(217, 20, 20, 24) }
    private val namePaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 220, 140); textSize = Layout.MIN_TEXT_PX; isFakeBoldText = true
    }
    private val chipPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = context.dp(13).toFloat() }
    private val basePx = context.dp(16).toFloat()
    private val pad = context.dp(4).toFloat()
    var translating = true
        private set

    fun add(seg: Segment) {
        val rect = RectF(seg.left, seg.top, seg.right, seg.bottom)
        if (seg.kind == Kind.NAME) {
            blocks.add(Block(seg, rect, null))
        } else {
            val text = seg.translation ?: ""
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
            blocks.add(Block(seg, rect, layout))
        }
        invalidate()
    }

    fun finish() {
        translating = false
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        for (b in blocks) {
            if (b.layout == null) {
                canvas.drawText(b.segment.source, b.rect.left, b.rect.bottom - namePaint.descent(), namePaint)
                continue
            }
            canvas.drawRoundRect(b.rect, pad, pad, bg)
            canvas.save()
            canvas.translate(b.rect.left + pad, b.rect.top + pad)
            b.layout.draw(canvas)
            canvas.restore()
        }
        if (translating) {
            val label = "Đang dịch…"
            val w = chipPaint.measureText(label) + 2 * pad * 3
            val r = RectF(width - w - pad * 4, pad * 12, width - pad * 4, pad * 12 + chipPaint.textSize * 2)
            canvas.drawRoundRect(r, pad * 2, pad * 2, bg)
            canvas.drawText(label, r.left + pad * 3, r.centerY() - (chipPaint.descent() + chipPaint.ascent()) / 2, chipPaint)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (e.actionMasked != MotionEvent.ACTION_UP) return true
        val hit = blocks.lastOrNull { it.layout != null && it.rect.contains(e.x, e.y) }
        if (hit == null) onClose() else onBlockTapped(hit.segment)
        return true
    }
}
