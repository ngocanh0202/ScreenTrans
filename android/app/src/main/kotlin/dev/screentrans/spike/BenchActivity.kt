package dev.screentrans.spike

import ai.onnxruntime.OrtSession
import android.app.Activity
import android.os.Bundle
import android.os.Debug
import android.os.SystemClock
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.gson.JsonParser
import screentrans.mt.Translator
import java.io.File
import kotlin.concurrent.thread

/**
 * Phase 0 spike C: measures opus-mt ONNX on the phone. The user taps "Chạy" and sends a
 * screenshot of the report. Throwaway — the real app is built in Phase 4.
 */
class BenchActivity : Activity() {
    private lateinit var out: TextView
    private lateinit var run: Button

    private data class Config(val name: String, val threads: Int, val configure: (OrtSession.SessionOptions) -> Unit = {})

    private val configs = listOf(
        Config("CPU 2 luồng", 2),
        Config("CPU 4 luồng", 4),
        Config("XNNPACK 2 luồng", 2) { it.addXnnpack(mapOf("intra_op_num_threads" to "2")) },
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        out = TextView(this).apply { setTextIsSelectable(true); textSize = 13f; setPadding(32, 32, 32, 32) }
        run = Button(this).apply { text = "Chạy"; setOnClickListener { start() } }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(run, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(ScrollView(context).apply { addView(out) }, LinearLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        }
        setContentView(root)
        out.text = "Bấm \"Chạy\" để đo (khoảng 1–3 phút). Đừng tắt màn hình."
    }

    private fun log(line: String) = runOnUiThread { out.append(line + "\n") }

    private fun start() {
        run.isEnabled = false
        out.text = ""
        thread(name = "bench") {
            try {
                bench()
            } catch (t: Throwable) {
                log("LỖI: ${t.javaClass.simpleName}: ${t.message}")
            } finally {
                runOnUiThread { run.isEnabled = true }
            }
        }
    }

    private fun copyModel(): File {
        val dir = File(filesDir, "model")
        dir.mkdirs()
        for (name in assets.list("model").orEmpty()) {
            val dst = File(dir, name)
            if (dst.exists()) continue
            assets.open("model/$name").use { input -> dst.outputStream().use { input.copyTo(it) } }
        }
        return dir
    }

    private fun bench() {
        log("Thiết bị: ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}, Android ${android.os.Build.VERSION.RELEASE}, ${Runtime.getRuntime().availableProcessors()} lõi")
        val t0 = SystemClock.elapsedRealtime()
        val dir = copyModel()
        log("Copy model: ${SystemClock.elapsedRealtime() - t0} ms, ${dir.listFiles().orEmpty().sumOf { it.length() } / 1_000_000} MB")

        val sentences = File(dir, "sentences.txt").readLines().filter { it.isNotBlank() }.take(20)
        val golden = JsonParser.parseString(File(dir, "golden_opus.json").readText()).asJsonArray
            .associate { it.asJsonObject["text"].asString to it.asJsonObject["out_text"].asString }
        val pss0 = Debug.getPss() / 1024

        for (cfg in configs) {
            log("\n== ${cfg.name} ==")
            val tl = SystemClock.elapsedRealtime()
            val tr = try {
                Translator(dir, cfg.threads, cfg.configure)
            } catch (t: Throwable) {
                log("Không tạo được session: ${t.message}")
                continue
            }
            tr.use {
                log("Load: ${SystemClock.elapsedRealtime() - tl} ms")
                it.translate("Hello.") // warm-up
                val times = ArrayList<Long>()
                var match = 0
                val samples = ArrayList<String>()
                for (s in sentences) {
                    var text = ""
                    repeat(3) { _ ->
                        val ts = SystemClock.elapsedRealtime()
                        text = it.translate(s)
                        times.add(SystemClock.elapsedRealtime() - ts)
                    }
                    if (norm(text) == norm(golden[s] ?: "")) match++
                    if (samples.size < 3) samples.add("$s\n→ $text")
                }
                times.sort()
                log("ms/câu: trung vị ${times[times.size / 2]}, p95 ${times[(times.size * 95) / 100 - 1]}, max ${times.last()}")
                log("Khớp golden: $match/${sentences.size}")
                log("RAM (PSS) app: ${Debug.getPss() / 1024} MB (trước khi load: $pss0 MB)")
                if (cfg === configs.first()) samples.forEach { s -> log(s) }
            }
        }
        log("\nXONG. Chụp màn hình gửi lại.")
    }

    private fun norm(s: String) = s.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
}
