package dev.screentrans.core.model

import com.google.gson.JsonParser
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import org.junit.jupiter.api.io.TempDir
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ModelStoreTest {
    @TestFactory
    fun catalog(): List<DynamicTest> {
        val file = File(System.getProperty("shared.dir"), "fixtures/model_catalog/catalog.json")
        return JsonParser.parseString(file.readText()).asJsonArray.map { it.asJsonObject }.map { c ->
            DynamicTest.dynamicTest(c["name"].asString) {
                val manifest = c["manifest"].asJsonArray.map { it.asJsonObject }.map { m ->
                    ManifestModel(m["id"].asString, m["version"].asString, m["label"]?.asString,
                        m["files"].asJsonArray.mapIndexed { i, f -> ManifestFile("f$i", size = f.asJsonObject["size"].asLong) })
                }
                val installed = c["installed"].asJsonObject.entrySet().associate { (k, v) -> k to v.asJsonArray.map { it.asString } }
                val bundled = c["bundled"].asJsonObject.entrySet().associate { (k, v) -> k to v.asString }
                val exp = c["rows"].asJsonArray.map { it.asJsonObject }.map { r ->
                    ModelRow(r["id"].asString, r["label"].asString, r["status"].asString,
                        r["version"].takeIf { !it.isJsonNull }?.asString, r["latest"].takeIf { !it.isJsonNull }?.asString,
                        r["download"].asLong, r["deletable"].asBoolean, r["active"].asBoolean)
                }
                assertEquals(exp, ModelCatalog.rows(manifest, installed, bundled, c["active"].asString))
            }
        }
    }

    private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    private val files = mapOf("enc.onnx" to "weights".repeat(50).toByteArray(), "sub/vocab.json" to "{}".toByteArray())

    private fun model(version: String, badSha: Boolean = false) = ManifestModel("st", version, "ST",
        files.map { (p, b) -> ManifestFile(p, "https://x/$p", if (badSha) "0".repeat(64) else sha(b), b.size.toLong()) })

    private val manifestJson = """{"version":1,"models":[
        {"id":"st","platform":"android","version":"2","label":"ST","files":[{"path":"a","url":"u","sha256":"${"0".repeat(64)}","size":3}]},
        {"id":"st","platform":"windows","version":"2","files":[]}]}"""

    private fun store(dir: File) = ModelStore(dir) { url ->
        if (url.endsWith("manifest.json")) manifestJson.byteInputStream()
        else files.getValue(url.removePrefix("https://x/")).inputStream()
    }

    @Test
    fun `download verifies, marks complete, lists, replaces old versions, deletes`(@TempDir dir: File) {
        val s = store(dir)
        val progress = mutableListOf<Long>()
        val v1 = s.download(model("1")) { done, _ -> progress.add(done) }
        assertEquals(files.getValue("sub/vocab.json").toList(), File(v1, "sub/vocab.json").readBytes().toList())
        assertEquals(mapOf("st" to listOf("1")), s.installed())
        assertEquals(files.values.sumOf { it.size }.toLong(), progress.last())
        val v2 = s.download(model("2"))
        assertFalse(v1.exists())
        assertEquals(v2, s.dirFor("st"))
        s.delete("st")
        assertEquals(emptyMap(), s.installed())
    }

    @Test
    fun `a wrong checksum leaves nothing installed`(@TempDir dir: File) {
        val s = store(dir)
        assertFailsWith<IOException> { s.download(model("1", badSha = true)) }
        assertEquals(emptyMap(), s.installed())
        assertTrue(dir.walk().none { it.name.endsWith(".part") })
    }

    @Test
    fun `manifest keeps this platform only`(@TempDir dir: File) {
        val m = store(dir).manifest("https://hf/manifest.json")
        assertEquals(listOf("st" to "2"), m.map { it.id to it.version })
        assertEquals("ST", m.single().label)
    }
}
