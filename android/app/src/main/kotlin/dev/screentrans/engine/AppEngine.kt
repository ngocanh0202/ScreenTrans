package dev.screentrans.engine

import android.content.Context
import android.graphics.Bitmap
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import dev.screentrans.core.EngineBundle
import dev.screentrans.core.ModelInstall
import screentrans.mt.Translator
import screentrans.text.Glossary
import screentrans.text.Line
import screentrans.text.Pipeline
import screentrans.text.ProperNounTracker
import screentrans.text.SentenceTranslator
import screentrans.text.TranslationCache
import screentrans.text.splitLong
import java.io.File

/** ML Kit Latin text recognition (bundled model, no Play Services download). Call off the main thread. */
class MlKitOcr {
    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    fun recognize(bitmap: Bitmap): List<Line> {
        val text = Tasks.await(recognizer.process(InputImage.fromBitmap(bitmap, 0)))
        return text.textBlocks.flatMap { block ->
            block.lines.mapNotNull { line ->
                val b = line.boundingBox ?: return@mapNotNull null
                Line(line.text, b.left.toFloat(), b.top.toFloat(), b.width().toFloat(), b.height().toFloat())
            }
        }
    }
}

/** Copies assets/model/ to filesDir/model/ when the bundled VERSION differs from the installed one. */
object ModelInstaller {
    fun install(context: Context): File {
        val bundled = context.assets.open("model/VERSION").bufferedReader().readText().trim()
        val dir = File(context.filesDir, "model")
        val versionFile = File(dir, "VERSION")
        val installed = if (versionFile.isFile) versionFile.readText().trim() else null
        if (!ModelInstall.needsCopy(installed, bundled)) return dir
        dir.deleteRecursively()
        dir.mkdirs()
        for (name in context.assets.list("model").orEmpty()) {
            if (name == "VERSION") continue
            val tmp = File(dir, "$name.part")
            context.assets.open("model/$name").use { input -> tmp.outputStream().use { input.copyTo(it) } }
            check(tmp.renameTo(File(dir, name))) { "cannot install $name" }
        }
        versionFile.writeText(bundled)  // last: a half-copied model is never marked as installed
        return dir
    }
}

object AppEngine {
    const val MODEL_ID = "opus-mt-en-vi"

    private fun asset(context: Context, path: String) = context.assets.open(path).bufferedReader().readText()

    /** Built on the engine thread: copies the model if needed, loads ONNX, glossaries and OCR. */
    fun bundle(context: Context): EngineBundle<Bitmap> {
        val modelDir = ModelInstaller.install(context)
        val mt = Translator(modelDir, threads = 2)
        val translator = SentenceTranslator { texts ->
            texts.map { text ->
                if (text.isBlank()) "" else splitLong(text, mt::countTokens).joinToString(" ") { mt.translate(it) }
            }
        }
        val games = context.assets.list("glossary/games").orEmpty().sorted().map { asset(context, "glossary/games/$it") }
        val glossary = Glossary.load(*(games + asset(context, "glossary/common.json")).toTypedArray())
        val common = asset(context, "glossary/common_words_en.txt").lines().map { it.trim().lowercase() }.toSet()
        val pipeline = Pipeline(translator, MODEL_ID, glossary, TranslationCache(5000), ProperNounTracker(common))
        val ocr = MlKitOcr()
        return EngineBundle(ocr = ocr::recognize, pipeline = pipeline, warmUp = { mt.translate("Hello.") })
    }
}
