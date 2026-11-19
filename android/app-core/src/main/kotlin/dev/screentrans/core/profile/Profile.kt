package dev.screentrans.core.profile

import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonNull
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.gson.JsonPrimitive
import screentrans.text.normalizeText
import kotlin.math.roundToLong

/**
 * Per-game profile — port of windows/app/profiles.py; reading rules in shared/fixtures/profiles/README.md.
 * Regions are [x, y, w, h] relative (0-1) to the screen.
 */
data class Profile(
    val id: String,
    val name: String = "",
    val scope: String = "region",
    /** Live colours: "match" (sampled from the game) or "classic" (white on dark); font size always matches. */
    val style: String = "match",
    /** OCR engine for this game: "auto" = the platform default (Android: mlkit). */
    val ocr: String = "auto",
    val engine: String = "local",  // translation engine: local | gemini | openai | claude | kaggle
    val regions: List<List<Double>> = emptyList(),
    val ignore: List<List<Double>> = emptyList(),
    val intervalMs: Int = 300,
    val settleMs: Int = 250,
    val changeThreshold: Double = 5.0,
    val glossary: String? = null,
    val overrides: Map<String, String> = emptyMap(),
) {
    fun serialize(): String = JsonObject().apply {
        addProperty("id", id)
        addProperty("name", name)
        addProperty("ocr", ocr)
        addProperty("engine", engine)
        add("live", JsonObject().apply {
            addProperty("scope", scope)
            addProperty("style", style)
            addProperty("interval_ms", intervalMs)
            addProperty("settle_ms", settleMs)
            addProperty("change_threshold", changeThreshold)
        })
        add("regions", rects(regions))
        add("ignore_regions", rects(ignore))
        add("glossary", glossary?.let { JsonPrimitive(it) } ?: JsonNull.INSTANCE)
        add("overrides", JsonObject().apply { overrides.forEach { (k, v) -> addProperty(k, v) } })
    }.toString()

    companion object {
        const val DEFAULT_ID = "_default"
        private val SCOPES = setOf("region", "screen")
        val ENGINES = setOf("local", "gemini", "openai", "claude", "kaggle")
        private val STYLES = setOf("match", "classic")

        private fun rects(list: List<List<Double>>) = JsonArray().apply {
            list.forEach { r -> add(JsonArray().apply { r.forEach { add(it) } }) }
        }

        private fun round6(v: Double) = (v * 1e6).roundToLong() / 1e6

        private fun num(e: JsonElement?): Double? {
            if (e == null || !e.isJsonPrimitive || !e.asJsonPrimitive.isNumber) return null
            return e.asDouble.takeIf { it.isFinite() }
        }

        private fun rel(e: JsonElement): List<Double>? {
            if (!e.isJsonArray || e.asJsonArray.size() != 4) return null
            val n = e.asJsonArray.map { num(it) ?: return null }
            val x = n[0].coerceIn(0.0, 1.0)
            val y = n[1].coerceIn(0.0, 1.0)
            val w = n[2].coerceIn(0.0, 1.0 - x)
            val h = n[3].coerceIn(0.0, 1.0 - y)
            if (w <= 0 || h <= 0) return null
            return listOf(round6(x), round6(y), round6(w), round6(h))
        }

        private fun rels(e: JsonElement?): List<List<Double>> =
            if (e == null || !e.isJsonArray) emptyList() else e.asJsonArray.mapNotNull { rel(it) }

        private fun positiveInt(e: JsonElement?, default: Int): Int {
            val n = num(e) ?: return default
            return if (n > 0 && n == Math.floor(n)) n.toInt() else default
        }

        private fun str(e: JsonElement?): String? =
            if (e != null && e.isJsonPrimitive && e.asJsonPrimitive.isString) e.asString else null

        /** Null when [text] is not a JSON object with a non-empty string "id". */
        fun parse(text: String): Profile? {
            val root = runCatching { JsonParser.parseString(text) }.getOrNull() ?: return null
            if (!root.isJsonObject) return null
            val o = root.asJsonObject
            val id = str(o["id"])?.takeIf { it.isNotEmpty() } ?: return null
            val live = o["live"]?.takeIf { it.isJsonObject }?.asJsonObject ?: JsonObject()
            val overrides = o["overrides"]?.takeIf { it.isJsonObject }?.asJsonObject ?: JsonObject()
            return Profile(
                id = id,
                name = str(o["name"]) ?: "",
                ocr = str(o["ocr"])?.takeIf { it.isNotEmpty() } ?: "auto",
                engine = str(o["engine"])?.takeIf { it in ENGINES } ?: "local",
                scope = str(live["scope"])?.takeIf { it in SCOPES } ?: "region",
                style = str(live["style"])?.takeIf { it in STYLES } ?: "match",
                regions = rels(o["regions"]),
                ignore = rels(o["ignore_regions"]),
                intervalMs = positiveInt(live["interval_ms"], 300),
                settleMs = positiveInt(live["settle_ms"], 250),
                changeThreshold = num(live["change_threshold"])?.takeIf { it > 0 } ?: 5.0,
                glossary = str(o["glossary"]),
                overrides = buildMap {
                    for ((k, v) in overrides.entrySet()) {
                        val key = normalizeText(k)
                        val value = str(v)
                        if (key.isNotEmpty() && value != null) put(key, value)
                    }
                },
            )
        }
    }
}
