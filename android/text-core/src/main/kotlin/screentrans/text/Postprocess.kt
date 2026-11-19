package screentrans.text

import kotlin.math.abs

/**
 * OCR lines -> paragraphs (name / text) -> sentences. Port of windows/app/text/postprocess.py;
 * the rules live in shared/fixtures/postprocess/README.md and both versions pass the same fixtures.
 */
/** [angle]: degrees, clockwise; the box is in the frame rotated by -angle ([Deskew]). */
data class Line(val text: String, val left: Float, val top: Float, val width: Float, val height: Float, val angle: Float = 0f) {
    val right: Float get() = left + width
    val bottom: Float get() = top + height
}

enum class Kind { NAME, TEXT }

data class Paragraph(
    val kind: Kind,
    val text: String,
    val sentences: List<String>,
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
    /** Median height of the OCR lines (Live: the translation uses the same font size). */
    val lineHeight: Float = 0f,
    /** Tilted text: the box is in the frame rotated by -angle ([Deskew]). */
    val angle: Float = 0f,
)

object Postprocess {
    const val JOIN_GAP = 0.8f
    const val OVERLAP = 0.5f
    const val NAME_GAP = 2.0f
    const val SAME_ROW = 0.5f

    private val WS = Regex("[\\s\\p{Z}\\u0085\\u001c-\\u001f]+")  // Android regex (ICU) lacks the U inline flag: Unicode spaces like Python str.split
    private const val JUNK_BRACKETS = "()[]{}<>|©®"
    private const val END_PUNCT = ".!?,;…\"'”’"
    private val NAME_TOKEN = Regex("^(?:[A-Z]|[IVXLl1|]{1,4}$)")
    private val ROMAN_MISREAD = Regex("^[Il1|]{2,4}$")
    private val NO_SPLIT = setOf("mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "etc.")
    private val SENT_END = Regex("[.!?…]+[\"”’']*")
    private val LONE_INITIAL = Regex("[A-Z]\\.")
    private val HYPHEN_END = Regex("[a-z]-$")

    private class Group(first: Line) {
        val lines = mutableListOf(first)
        val left get() = lines.minOf { it.left }
        val right get() = lines.maxOf { it.right }
        val top get() = lines.minOf { it.top }
        val bottom get() = lines.maxOf { it.bottom }
        val lineHeight: Float get() {
            val hs = lines.map { it.height }.sorted()
            val n = hs.size
            return if (n == 0) 0f else if (n % 2 == 1) hs[n / 2] else (hs[n / 2 - 1] + hs[n / 2]) / 2
        }
    }

    private fun tokens(s: String): List<String> = s.trim().split(WS).filter { it.isNotEmpty() }

    private fun clean(text: String): String {
        val t = tokens(text).toMutableList()
        while (t.isNotEmpty() && (t.first().none { it.isLetterOrDigit() } ||
                    (t.first().length <= 2 && t.first().any { it in JUNK_BRACKETS }))) t.removeAt(0)
        while (t.isNotEmpty() && t.last().none { it.isLetterOrDigit() }) t.removeAt(t.size - 1)
        return t.joinToString(" ")
    }

    private fun join(lines: List<Line>): String {
        var out = ""
        for (line in lines) {
            val t = tokens(line.text).joinToString(" ")
            out = when {
                out.isEmpty() -> t
                HYPHEN_END.containsMatchIn(out) && t.firstOrNull()?.isLowerCase() == true -> out.dropLast(1) + t
                else -> "$out $t"
            }
        }
        return out
    }

    fun splitSentences(text: String): List<String> {
        val s = tokens(text).joinToString(" ")
        if (s.isEmpty()) return emptyList()
        val out = mutableListOf<String>()
        var start = 0
        for (m in SENT_END.findAll(s)) {
            val end = m.range.last + 1
            val rest = s.substring(end)
            if (!(rest.startsWith(" ") && rest.length > 1 && (rest[1].isUpperCase() || rest[1] in "\"“"))) continue
            val token = s.substring(0, end).split(" ").last().trimStart('"', '“', '‘', '\'', '(')
            if (token.lowercase() in NO_SPLIT || LONE_INITIAL.matches(token)) continue
            out.add(s.substring(start, end).trim())
            start = end + 1
        }
        val tail = s.substring(start).trim()
        if (tail.isNotEmpty()) out.add(tail)
        return out
    }

    private fun isName(g: Group, text: String, groups: List<Group>, h: Float): Boolean {
        val toks = tokens(text.trimEnd(':'))
        if (g.lines.size != 1 || toks.size !in 1..3) return false
        if (!toks.all { NAME_TOKEN.containsMatchIn(it) }) return false
        if (text.endsWith(":")) return true
        if (text.isNotEmpty() && text.last() in END_PUNCT) return false
        return groups.any { o ->
            o !== g && o.top - g.bottom in 0f..NAME_GAP * h && o.left < g.right + h && o.right > g.left - h
        }
    }

    private fun nameText(text: String): String =
        tokens(text.trimEnd(':')).joinToString(" ") { if (ROMAN_MISREAD.matches(it)) "I".repeat(it.length) else it }

    /** Same as Python statistics.median: mean of the two middle values for an even count. */
    private fun median(values: List<Float>): Float {
        val v = values.sorted()
        val mid = v.size / 2
        return if (v.size % 2 == 1) v[mid] else (v[mid - 1] + v[mid]) / 2f
    }

    private const val MAX_TILT = 60f   // more than this is vertical text / noise: dropped
    private const val SAME_TILT = 2f   // lines within this many degrees share a tilted frame

    /** Paragraphs of the OCR lines; tilted lines are grouped per angle (shared fixtures README). */
    fun run(lines: List<Line>): List<Paragraph> {
        val clusters = mutableListOf<MutableList<Line>>()
        for (line in lines.filter { abs(it.angle) <= MAX_TILT }.sortedBy { it.angle }) {
            val last = clusters.lastOrNull()  // a new cluster where neighbouring angles are SAME_TILT or more apart
            if (last != null && line.angle - last.last().angle < SAME_TILT) last.add(line) else clusters.add(mutableListOf(line))
        }
        val parts = clusters.mapNotNull { cluster ->
            val a = median(cluster.map { it.angle })
            val angle = if (abs(a) < SAME_TILT) 0f else a
            // express every line in the cluster's frame: measured angles differ a little per line
            val reprojected = cluster.map { l ->
                if (l.angle == angle) l else {
                    val (sx, sy) = Deskew.unrotate(l.left + l.width / 2, l.top + l.height / 2, l.angle)
                    val (cx, cy) = Deskew.rotate(sx, sy, angle)
                    Line(l.text, cx - l.width / 2, cy - l.height / 2, l.width, l.height, angle)
                }
            }
            val paras = runFrame(reprojected).map { it.copy(angle = angle) }
            paras.firstOrNull()?.let { first -> Deskew.unrotate(first.left, first.top, angle).second to paras }
        }
        return parts.sortedBy { it.first }.flatMap { it.second }
    }

    /** The straight-text rules, for lines that share one (possibly tilted) frame. */
    private fun runFrame(lines: List<Line>): List<Paragraph> {
        val cleaned = lines.mapNotNull { line ->
            val t = clean(line.text)
            if (t.any { it.isLetter() } && t.length > 1) Line(t, line.left, line.top, line.width, line.height, line.angle) else null
        }
        if (cleaned.isEmpty()) return emptyList()
        val h = median(cleaned.map { it.height })

        val groups = mutableListOf<Group>()
        for (line in cleaned.sortedWith(compareBy({ it.top }, { it.left }))) {
            val fits = groups.filter {
                line.top - it.bottom in -OVERLAP * h..JOIN_GAP * h && line.left in it.left - h..it.right
            }
            val target = fits.maxByOrNull { it.bottom }  // first of equal maxima = created first
            if (target != null) target.lines.add(line) else groups.add(Group(line))
        }

        groups.sortBy { it.top }  // stable, like Python
        var i = 1
        while (i < groups.size) {  // adjacent paragraphs on the same row: left first
            val a = groups[i - 1]
            val b = groups[i]
            if (kotlin.math.abs(a.top - b.top) < SAME_ROW * h && b.left < a.left) {
                groups[i - 1] = b
                groups[i] = a
                i = maxOf(1, i - 1)
            } else {
                i++
            }
        }

        return groups.map { g ->
            val text = join(g.lines)
            if (isName(g, text, groups, h)) Paragraph(Kind.NAME, nameText(text), emptyList(), g.left, g.top, g.right, g.bottom, g.lineHeight)
            else Paragraph(Kind.TEXT, text, splitSentences(text), g.left, g.top, g.right, g.bottom, g.lineHeight)
        }
    }
}
