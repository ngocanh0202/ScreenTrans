package screentrans.mt

import com.google.gson.JsonParser
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals

class GoldenTest {
    private val modelDir = File(System.getProperty("mt.modelDir") ?: "")
    private val goldenFile = File(System.getProperty("mt.golden") ?: "")

    private data class Golden(val text: String, val srcIds: IntArray, val outIds: IntArray, val outText: String)

    private fun golden(): List<Golden> {
        assumeTrue(goldenFile.isFile && File(modelDir, "decoder_model_merged.onnx").isFile, "model/golden not exported; skipping")
        return JsonParser.parseString(goldenFile.readText()).asJsonArray.map { e ->
            val o = e.asJsonObject
            Golden(
                o["text"].asString,
                o["src_ids"].asJsonArray.map { it.asInt }.toIntArray(),
                o["out_ids"].asJsonArray.map { it.asInt }.toIntArray(),
                o["out_text"].asString,
            )
        }
    }

    private fun norm(s: String) = s.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")

    @Test
    fun `tokenizer matches python ids`() {
        val items = golden()
        val sp = SentencePieceUnigram(File(modelDir, "sp_source.json").readText())
        val vocab = MarianVocab(File(modelDir, "vocab.json").readText())
        val mismatched = items.filter { !vocab.ids(sp.encode(it.text)).contentEquals(it.srcIds) }
        mismatched.firstOrNull()?.let {
            println("first mismatch: '${it.text}'\n  kotlin=${vocab.ids(sp.encode(it.text)).toList()}\n  python=${it.srcIds.toList()}")
        }
        assertEquals(0, mismatched.size, "${mismatched.size}/${items.size} sentences tokenized differently")
    }

    @Test
    fun `greedy decode matches python`() {
        val items = golden()
        OrtSeq2Seq(modelDir).use { model ->
            for (g in items) {
                val out = greedyDecode(model, g.srcIds, model.startId, model.eosId, model.padId)
                assertContentEquals(g.outIds, out, "decode differs for '${g.text}'")
            }
        }
    }

    @Test
    fun `decode text matches python`() {
        val items = golden()
        val vocab = MarianVocab(File(modelDir, "vocab.json").readText())
        for (g in items) assertEquals(norm(g.outText), norm(vocab.decode(g.outIds)))
    }

    @Test
    fun `translator end to end`() {
        val items = golden()
        Translator(modelDir).use { tr ->
            assertEquals(norm(items[0].outText), norm(tr.translate(items[0].text)))
        }
    }

    @Test
    fun `fake model stops at maxLen`() {
        val fake = object : Seq2SeqModel {
            override fun start(srcIds: IntArray): DecoderState = DecoderState.NONE
            override fun step(state: DecoderState, lastToken: Int): Pair<FloatArray, DecoderState> =
                FloatArray(10).also { it[5] = 1f } to DecoderState.NONE
        }
        val out = greedyDecode(fake, intArrayOf(1, 0), startId = 9, eosId = 0, padId = 9, maxLen = 7)
        assertEquals(7, out.size)
        assertEquals(listOf(5), out.distinct())
    }

    @Test
    fun `pad token is never generated`() {
        val fake = object : Seq2SeqModel {
            override fun start(srcIds: IntArray): DecoderState = DecoderState.NONE
            override fun step(state: DecoderState, lastToken: Int): Pair<FloatArray, DecoderState> =
                FloatArray(10).also { it[9] = 5f; it[0] = 1f } to DecoderState.NONE
        }
        assertContentEquals(intArrayOf(0), greedyDecode(fake, intArrayOf(1, 0), startId = 9, eosId = 0, padId = 9))
    }

    @Test
    fun `empty input is not sent to the model`() {
        assertEquals("", Translator.blankOrNull(""))
        assertEquals("", Translator.blankOrNull("   "))
        assertEquals(null, Translator.blankOrNull("Hi"))
    }
}
