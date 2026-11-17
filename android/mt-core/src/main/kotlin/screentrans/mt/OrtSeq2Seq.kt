package screentrans.mt

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import com.google.gson.JsonParser
import java.io.File
import java.nio.FloatBuffer
import java.nio.LongBuffer

/**
 * ONNX Runtime Marian: encoder_model.onnx + decoder_model_merged.onnx (KV cache).
 * Uses only the ai.onnxruntime Java API, identical on desktop JVM and Android.
 */
class OrtSeq2Seq(
    modelDir: File,
    threads: Int = 2,
    configure: (OrtSession.SessionOptions) -> Unit = {},
) : Seq2SeqModel, AutoCloseable {
    private val env = OrtEnvironment.getEnvironment()
    private val opts = OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(threads)
        setInterOpNumThreads(1)
        configure(this)
    }
    private val encoder = env.createSession(File(modelDir, "encoder_model.onnx").path, opts)
    private val decoder = env.createSession(File(modelDir, "decoder_model_merged.onnx").path, opts)
    private val pastNames = decoder.inputNames.filter { it.startsWith("past_key_values") }.sorted()

    val startId: Int
    val eosId: Int
    val padId: Int
    private val heads: Int
    private val headDim: Int

    init {
        val cfg = JsonParser.parseString(File(modelDir, "config.json").readText()).asJsonObject
        startId = cfg["decoder_start_token_id"].asInt
        eosId = cfg["eos_token_id"].asInt
        padId = cfg["pad_token_id"].asInt
        heads = cfg["decoder_attention_heads"].asInt
        headDim = cfg["d_model"].asInt / heads
    }

    /** Resources shared by every step of one translation; freed when the last state closes. */
    private class Run(val encoderOut: OnnxTensor, val mask: OnnxTensor, private val owned: MutableList<AutoCloseable>) {
        private var refs = 0
        fun retain() { refs++ }
        fun release() { if (--refs == 0) owned.forEach { it.close() } }
        fun own(c: AutoCloseable) { owned.add(c) }
    }

    private class State(
        val run: Run,
        val past: Map<String, OnnxTensor>,
        val useCache: Boolean,
        private val ownedResult: AutoCloseable?,
    ) : DecoderState {
        init { run.retain() }
        private var closed = false
        override fun close() {
            if (closed) return
            closed = true
            ownedResult?.close()
            run.release()
        }
    }

    override fun start(srcIds: IntArray): DecoderState {
        val n = srcIds.size.toLong()
        val mask = OnnxTensor.createTensor(env, LongBuffer.wrap(LongArray(srcIds.size) { 1L }), longArrayOf(1, n))
        val encResult = try {
            OnnxTensor.createTensor(env, LongBuffer.wrap(LongArray(srcIds.size) { srcIds[it].toLong() }), longArrayOf(1, n))
                .use { ids -> encoder.run(mapOf("input_ids" to ids, "attention_mask" to mask)) }
        } catch (t: Throwable) {
            mask.close()
            throw t
        }
        val empty = pastNames.associateWith {
            OnnxTensor.createTensor(env, FloatBuffer.allocate(0), longArrayOf(1, heads.toLong(), 0, headDim.toLong()))
        }
        val run = Run(encResult[0] as OnnxTensor, mask, mutableListOf(encResult, mask))
        empty.values.forEach { run.own(it) }
        return State(run, empty, useCache = false, ownedResult = null)
    }

    override fun step(state: DecoderState, lastToken: Int): Pair<FloatArray, DecoderState> {
        val s = state as State
        val feeds = HashMap<String, OnnxTensor>(s.past)
        val input = OnnxTensor.createTensor(env, LongBuffer.wrap(longArrayOf(lastToken.toLong())), longArrayOf(1, 1))
        val useCache = OnnxTensor.createTensor(env, booleanArrayOf(s.useCache))
        feeds["input_ids"] = input
        feeds["encoder_attention_mask"] = s.run.mask
        feeds["encoder_hidden_states"] = s.run.encoderOut
        feeds["use_cache_branch"] = useCache
        val result = try { decoder.run(feeds) } finally { input.close(); useCache.close() }

        @Suppress("UNCHECKED_CAST")
        val logits3 = (result[0] as OnnxTensor).value as Array<Array<FloatArray>>
        val logits = logits3[0][logits3[0].size - 1]

        val next = HashMap<String, OnnxTensor>()
        for (name in pastNames) {
            if (s.useCache && name.contains(".encoder.")) {
                // On cache steps the encoder KV outputs are dummies: keep the first step's.
                next[name] = s.past.getValue(name)
            } else {
                next[name] = result.get(name.replace("past_key_values", "present")).get() as OnnxTensor
            }
        }
        // The first step's result holds the encoder KV used by every later step: the run owns it.
        val nextState = if (!s.useCache) {
            s.run.own(result)
            State(s.run, next, useCache = true, ownedResult = null)
        } else {
            State(s.run, next, useCache = true, ownedResult = result)
        }
        return logits to nextState
    }

    override fun close() {
        encoder.close()
        decoder.close()
        opts.close()
    }
}
