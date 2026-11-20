package dev.screentrans.core.model

import com.google.gson.JsonParser
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** The app's model list on Hugging Face (same file as Windows; models/manifest.py publishes it). */
const val MANIFEST_URL = "https://huggingface.co/anhbui02/screentrans-models/resolve/main/manifest.json"

data class ManifestFile(val path: String, val url: String = "", val sha256: String = "", val size: Long = 0)
data class ManifestModel(val id: String, val version: String, val label: String?, val files: List<ManifestFile>)

/** One row of Settings → Model (port of windows/app/model_catalog.py, rules in shared/fixtures/model_catalog). */
data class ModelRow(
    val id: String, val label: String, val status: String, val version: String?, val latest: String?,
    val download: Long, val deletable: Boolean, val active: Boolean,
)

object ModelCatalog {
    fun rows(manifest: List<ManifestModel>, installed: Map<String, List<String>>, bundled: Map<String, String>,
             active: String): List<ModelRow> {
        val byId = manifest.associateBy { it.id }
        val ids = manifest.map { it.id } + ((installed.keys + bundled.keys) - byId.keys).sorted()
        return ids.map { id ->
            val m = byId[id]
            val versions = installed[id].orEmpty()
            val have = versions.toSet() + listOfNotNull(bundled[id])
            val latest = m?.version
            val status = when {
                have.isNotEmpty() && latest != null && latest !in have -> "update"
                have.isNotEmpty() -> if (versions.isNotEmpty() && (latest == null || latest in versions)) "installed" else "bundled"
                else -> "missing"
            }
            val size = if (m != null && (status == "missing" || status == "update")) m.files.sumOf { it.size } else 0L
            ModelRow(id, m?.label ?: id, status, versions.maxOrNull() ?: bundled[id], latest, size,
                versions.isNotEmpty(), id == active)
        }
    }
}

/**
 * Downloaded models under [root]/<id>/<version>/ (".complete" once every file is verified), like the Windows app.
 * [open] reads a URL (tests inject one).
 */
class ModelStore(private val root: File, private val open: (String) -> InputStream = ::httpOpen) {
    fun manifest(url: String = MANIFEST_URL, platform: String = "android"): List<ManifestModel> {
        val doc = JsonParser.parseString(open(url).use { it.readBytes().toString(Charsets.UTF_8) }).asJsonObject
        return doc["models"].asJsonArray.map { it.asJsonObject }.filter { it["platform"]?.asString == platform }.map { o ->
            ManifestModel(
                o["id"].asString, o["version"].asString, o["label"]?.asString,
                o["files"].asJsonArray.map { f ->
                    val x = f.asJsonObject
                    ManifestFile(x["path"].asString, x["url"].asString, x["sha256"].asString, x["size"].asLong)
                },
            )
        }
    }

    fun installed(): Map<String, List<String>> = root.listFiles().orEmpty().filter { it.isDirectory }.sortedBy { it.name }
        .associate { m -> m.name to m.listFiles().orEmpty().filter { File(it, COMPLETE).isFile }.map { it.name }.sorted() }
        .filterValues { it.isNotEmpty() }

    /** The newest complete version of [id], or null. */
    fun dirFor(id: String): File? = installed()[id]?.maxOrNull()?.let { File(File(root, id), it) }

    /** Every file of [m], verified by SHA-256; the old versions are removed afterwards. */
    fun download(m: ManifestModel, progress: (Long, Long) -> Unit = { _, _ -> }): File {
        val dir = File(File(root, m.id), m.version)
        val missing = m.files.filter { File(dir, it.path).let { f -> !f.isFile || f.length() != it.size } }
        val total = missing.sumOf { it.size }
        var done = 0L
        for (f in missing) {
            val dest = File(dir, f.path)
            dest.parentFile?.mkdirs()
            val part = File(dest.path + ".part")
            val digest = MessageDigest.getInstance("SHA-256")
            try {
                open(f.url).use { input ->
                    part.outputStream().use { out ->
                        val buf = ByteArray(1 shl 16)
                        while (true) {
                            val n = input.read(buf)
                            if (n < 0) break
                            out.write(buf, 0, n)
                            digest.update(buf, 0, n)
                            done += n
                            progress(done, total)
                        }
                    }
                }
            } catch (e: IOException) {
                part.delete()
                throw IOException("Tải ${f.path} lỗi (${e.message}). Thử lại sau.", e)
            }
            if (digest.digest().joinToString("") { "%02x".format(it) } != f.sha256) {
                part.delete()
                throw IOException("${f.path}: SHA-256 không khớp (file hỏng hoặc danh sách model đã đổi). Thử lại sau.")
            }
            if (!part.renameTo(dest)) {
                dest.delete()
                if (!part.renameTo(dest)) throw IOException("cannot save ${f.path}")
            }
        }
        File(dir, COMPLETE).writeText(m.version)
        File(root, m.id).listFiles().orEmpty().filter { it.isDirectory && it != dir }.forEach { it.deleteRecursively() }
        return dir
    }

    fun delete(id: String) {
        File(root, id).deleteRecursively()
    }

    companion object {
        const val COMPLETE = ".complete"

        fun httpOpen(url: String): InputStream = (URL(url).openConnection() as HttpURLConnection).run {
            connectTimeout = 30_000
            readTimeout = 60_000
            instanceFollowRedirects = true  // Hugging Face "resolve" URLs redirect to its file CDN
            if (responseCode !in 200..299) throw IOException("HTTP $responseCode")
            inputStream
        }
    }
}
