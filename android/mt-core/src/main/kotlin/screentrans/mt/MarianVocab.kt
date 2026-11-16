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

    /** Source ids for the encoder: pieces mapped through the vocab, unknown -> <unk>, then </s>. */
    fun ids(pieces: List<String>): IntArray = IntArray(pieces.size + 1) { i ->
        if (i == pieces.size) eosId else toId[pieces[i]] ?: unkId
    }

    /** Detokenize generated ids: drop special tokens, join pieces, '▁' -> space. */
    fun decode(ids: IntArray): String = ids
        .filter { it != eosId && it != padId && it != unkId }
        .joinToString("") { toPiece[it] ?: "" }
        .replace(SentencePieceUnigram.SPACE, " ")
        .trim()
}
