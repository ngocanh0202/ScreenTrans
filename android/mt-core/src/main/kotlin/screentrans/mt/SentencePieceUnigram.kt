package screentrans.mt

import com.google.gson.JsonParser
import java.text.Normalizer

/**
 * Pure-Kotlin SentencePiece unigram encoder (no native code), loaded from the JSON
 * written by models/sp_export.py. Mirrors spm defaults used by Marian:
 * nmt_nfkc normalization, remove extra whitespace, dummy prefix, Viterbi over piece scores.
 */
class SentencePieceUnigram(json: String) {
    private val pieces = HashMap<String, Float>()
    private val maxPieceLen: Int
    private val unkScore: Float

    init {
        val root = JsonParser.parseString(json).asJsonObject
        var minScore = 0f
        var maxLen = 1
        for (e in root["pieces"].asJsonArray) {
            val arr = e.asJsonArray
            val piece = arr[0].asString
            val score = arr[1].asFloat
            val type = arr[2].asInt
            if (type == NORMAL || type == USER_DEFINED) {
                pieces[piece] = score
                maxLen = maxOf(maxLen, piece.codePointCount(0, piece.length))
                minScore = minOf(minScore, score)
            }
        }
        maxPieceLen = maxLen
        unkScore = minScore - UNK_PENALTY
    }

    fun normalize(text: String): String {
        val nfkc = Normalizer.normalize(text, Normalizer.Form.NFKC)
        val sb = StringBuilder()
        // Measured against spm nmt_nfkc (source.spm): these become a space, everything else
        // (including control chars, ZWNJ/ZWJ, soft hyphen, word joiner) is kept as-is.
        for (ch in nfkc) sb.append(if (ch in SPM_SPACES) ' ' else ch)
        val collapsed = sb.toString().trim().split(Regex(" +")).filter { it.isNotEmpty() }.joinToString(" ")
        return if (collapsed.isEmpty()) "" else SPACE + collapsed.replace(" ", SPACE)
    }

    fun encode(text: String): List<String> {
        val s = normalize(text)
        if (s.isEmpty()) return emptyList()
        val cps = s.codePoints().toArray()
        val n = cps.size
        val best = FloatArray(n + 1) { Float.NEGATIVE_INFINITY }
        val back = IntArray(n + 1)
        best[0] = 0f
        for (end in 1..n) {
            for (len in 1..minOf(maxPieceLen, end)) {
                val start = end - len
                if (best[start] == Float.NEGATIVE_INFINITY) continue
                val sub = String(cps, start, len)
                val score = pieces[sub] ?: if (len == 1) unkScore else continue
                val cand = best[start] + score
                if (cand > best[end]) {
                    best[end] = cand
                    back[end] = start
                }
            }
        }
        val out = ArrayList<String>()
        var end = n
        while (end > 0) {
            val start = back[end]
            out.add(String(cps, start, end - start))
            end = start
        }
        out.reverse()
        return mergeUnknowns(out)
    }

    /** spm emits a run of consecutive unknown characters as a single piece. */
    private fun mergeUnknowns(tokens: List<String>): List<String> {
        val out = ArrayList<String>()
        for (t in tokens) {
            val unknown = t !in pieces
            if (unknown && out.isNotEmpty() && out.last() !in pieces) out[out.size - 1] = out.last() + t else out.add(t)
        }
        return out
    }

    companion object {
        const val SPACE = "▁"
        private val SPM_SPACES: Set<Char> = buildSet {
            addAll(listOf('\t', '\n', '\u000C', '\r', ' ', ' ', ' ', '​', '‎', '‏'))
            addAll(listOf(' ', ' ', ' ', ' ', '▁', '　', '﻿', '�'))
            addAll((' '..' '))
        }
        private const val NORMAL = 1
        private const val USER_DEFINED = 4
        private const val UNK_PENALTY = 10f
    }
}
