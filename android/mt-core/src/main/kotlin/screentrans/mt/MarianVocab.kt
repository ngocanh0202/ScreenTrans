package screentrans.mt

import com.google.gson.JsonParser

/** Marian shared vocabulary (vocab.json): piece <-> id, plus the special ids. */
class MarianVocab(json: String) {
    private val toId = HashMap<String, Int>()
    private val toPiece = HashMap<Int, String>()
    val eosId: Int
    val unkId: Int
    val padId: Int

    init {
        for ((piece, id) in JsonParser.parseString(json).asJsonObject.entrySet()) {
            toId[piece] = id.asInt
            toPiece[id.asInt] = piece
        }
        eosId = toId.getValue("</s>")
        unkId = toId.getValue("<unk>")
        padId = toId.getValue("<pad>")
    }

    companion object {
        /** Marian model_max_length: longer sources overflow the positional embeddings. */
        const val MAX_SRC = 512
    }

    /**
     * Source ids for the encoder: pieces mapped through the vocab, unknown -> <unk>, then </s>.
     * Truncated to MAX_SRC ids (like the HF tokenizer with truncation=True).
     */
    fun ids(pieces: List<String>): IntArray {
        val n = minOf(pieces.size, MAX_SRC - 1)
        return IntArray(n + 1) { i -> if (i == n) eosId else toId[pieces[i]] ?: unkId }
    }

    /** Detokenize generated ids: drop special tokens, join pieces, '▁' -> space. */
    fun decode(ids: IntArray): String = ids
        .filter { it != eosId && it != padId && it != unkId }
        .joinToString("") { toPiece[it] ?: "" }
        .replace(SentencePieceUnigram.SPACE, " ")
        .trim()
}
