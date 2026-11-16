package screentrans.mt

import ai.onnxruntime.OrtSession
import java.io.File

/** EN -> VI translator: SentencePiece -> ONNX Marian (greedy) -> detokenize. */
class Translator(
    modelDir: File,
    threads: Int = 2,
    configure: (OrtSession.SessionOptions) -> Unit = {},
) : AutoCloseable {
    private val sp = SentencePieceUnigram(File(modelDir, "sp_source.json").readText())
    private val vocab = MarianVocab(File(modelDir, "vocab.json").readText())
    private val model = OrtSeq2Seq(modelDir, threads, configure)

    fun translate(text: String, maxLen: Int = 256): String {
        blankOrNull(text)?.let { return it }
        val src = vocab.ids(sp.encode(text))
        return vocab.decode(greedyDecode(model, src, model.startId, model.eosId, model.padId, maxLen))
    }

    override fun close() = model.close()

    companion object {
        /** "" for blank input (never sent to the model), null otherwise. */
        fun blankOrNull(text: String): String? = if (text.isBlank()) "" else null
    }
}
