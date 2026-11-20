package screentrans.text

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.Strictness
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import java.io.StringReader

/**
 * Editing a game's own glossary in Settings (port of windows/app/text/term_edit.py, rules in
 * shared/fixtures/term_edit). [Row.target] null = keep the source as is.
 */
object TermEdit {
    data class Row(val source: String, val target: String?, val caseSensitive: Boolean = true)

    /** The rows of a glossary file; null when it is broken (not a JSON object with an "entries" array). */
    fun parse(text: String): List<Row>? {
        val root = try {
            val reader = JsonReader(StringReader(text)).apply { strictness = Strictness.STRICT }
            Gson().getAdapter(JsonElement::class.java).read(reader).also {
                if (reader.peek() != JsonToken.END_DOCUMENT) return null
            }
        } catch (e: Exception) {
            return null
        }
        val entries = (root as? JsonObject)?.get("entries") as? JsonArray ?: return null
        return entries.mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            val src = o["source"]?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString ?: return@mapNotNull null
            val type = o["type"]?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
            val target = o["target"]?.takeIf { type == "map" && it.isJsonPrimitive && it.asJsonPrimitive.isString }?.asString
            val cs = o["case_sensitive"]?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isBoolean }?.asBoolean ?: true
            Row(src, target, cs)
        }
    }

    /** Before saving: trimmed, empty sources dropped, empty targets = keep; a later duplicate (any case) replaces
     *  the earlier one in its place. */
    fun clean(rows: List<Row>): List<Row> {
        val out = mutableListOf<Row>()
        val where = HashMap<String, Int>()
        for (r in rows) {
            val source = r.source.trim().split(UNICODE_WS).filter { it.isNotEmpty() }.joinToString(" ")
            if (source.isEmpty()) continue
            val row = Row(source, r.target?.trim()?.ifEmpty { null }, r.caseSensitive)
            val key = source.lowercase()
            val at = where[key]
            if (at != null) out[at] = row else { where[key] = out.size; out.add(row) }
        }
        return out
    }

    fun dump(rows: List<Row>): String {
        val entries = JsonArray()
        for (r in rows) entries.add(JsonObject().apply {
            addProperty("source", r.source)
            addProperty("type", if (r.target.isNullOrEmpty()) "keep" else "map")
            if (!r.target.isNullOrEmpty()) addProperty("target", r.target)
            addProperty("case_sensitive", r.caseSensitive)
        })
        return GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(JsonObject().apply { add("entries", entries) })
    }
}
