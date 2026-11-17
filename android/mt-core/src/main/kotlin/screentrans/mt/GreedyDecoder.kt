package screentrans.mt

/** Opaque per-step decoder state (KV cache). Implementations release native memory in close(). */
interface DecoderState : AutoCloseable {
    override fun close() {}

    companion object {
        val NONE = object : DecoderState {}
    }
}

interface Seq2SeqModel {
    /** Run the encoder and return the state for the first decoder step. */
    fun start(srcIds: IntArray): DecoderState

    /** One decoder step: logits for the next token and the state for the step after. */
    fun step(state: DecoderState, lastToken: Int): Pair<FloatArray, DecoderState>
}

/**
 * Greedy decoding. Matches models/onnx_ref.py: the pad token is never generated
 * (Marian's bad_words_ids), stop at eos (included in the output) or after maxLen tokens.
 */
fun greedyDecode(
    model: Seq2SeqModel,
    srcIds: IntArray,
    startId: Int,
    eosId: Int,
    padId: Int,
    maxLen: Int = 256,
): IntArray {
    val out = ArrayList<Int>()
    var state = model.start(srcIds)
    var last = startId
    try {
        while (out.size < maxLen) {
            val (logits, next) = model.step(state, last)
            if (next !== state) state.close()
            state = next
            var best = -1
            var bestScore = Float.NEGATIVE_INFINITY
            for (i in logits.indices) {
                if (i == padId) continue
                if (logits[i] > bestScore) {
                    bestScore = logits[i]
                    best = i
                }
            }
            out.add(best)
            if (best == eosId) break
            last = best
        }
    } finally {
        state.close()
    }
    return out.toIntArray()
}
