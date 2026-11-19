package screentrans.text

import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import com.google.gson.stream.JsonReader
import java.io.StringReader

/** Prompt and reply rules for the remote LLM engines: shared/fixtures/llm (same as windows/app/translate/llm_prompt.py). */
object LlmPrompt {
    const val SYSTEM = "Bạn dịch lời thoại và chữ trong game từ tiếng Anh sang tiếng Việt. Dịch tự nhiên, đúng giọng " +
        "nhân vật, không thêm bớt ý. Giữ nguyên tên riêng. Trả về JSON {\"translations\": [...]}, mỗi câu đầu vào đúng " +
        "một bản dịch, cùng thứ tự."
    const val CONTEXT_MAX = 10
    const val EXAMPLES_MAX = 5
    const val REPLY_SCHEMA_JSON = "{\"type\":\"object\",\"properties\":{\"translations\":{\"type\":\"array\"," +
        "\"items\":{\"type\":\"string\"}}},\"required\":[\"translations\"],\"additionalProperties\":false}"

    private val gson = GsonBuilder().disableHtmlEscaping().create()

    /** Like Python json.dumps(list, ensure_ascii=False): ", " between items. */
    private fun jsonArray(items: List<String>) = items.joinToString(", ", "[", "]") { gson.toJson(it) }

    fun buildMessages(
        sentences: List<String>,
        context: List<Pair<String?, String>>,
        speaker: String?,
        glossary: Map<String, String?>,
        notes: String = "",
        examples: List<Pair<String, String>> = emptyList(),
    ): Pair<String, String> {
        val parts = mutableListOf<String>()
        if (notes.isNotBlank()) parts.add("Về game:\n" + notes.trim())
        if (glossary.isNotEmpty()) {
            parts.add("Thuật ngữ:\n" + glossary.entries.joinToString("\n") { (src, dst) ->
                if (dst == null) "- $src (giữ nguyên)" else "- $src → $dst"
            })
        }
        if (examples.isNotEmpty()) {
            parts.add("Cách dịch người dùng đã sửa (làm theo giọng này):\n" +
                examples.takeLast(EXAMPLES_MAX).joinToString("\n") { (src, fixed) -> "- $src → $fixed" })
        }
        if (context.isNotEmpty()) {
            parts.add("Câu trước (để hiểu ngữ cảnh, không dịch):\n" +
                context.takeLast(CONTEXT_MAX).joinToString("\n") { (sp, text) -> if (sp.isNullOrEmpty()) "- $text" else "- $sp: $text" })
        }
        if (!speaker.isNullOrEmpty()) parts.add("Người nói: $speaker")
        parts.add("Dịch các câu sau:\n" + jsonArray(sentences))
        return SYSTEM to parts.joinToString("\n\n")
    }

    /** The n translations in the model's reply, or null when it cannot be used as is. */
    fun parseReply(text: String, n: Int): List<String>? {
        val start = text.indexOfFirst { it == '[' || it == '{' }
        if (start < 0) return null
        val data = try {
            JsonParser.parseReader(JsonReader(StringReader(text.substring(start))))  // the first value; the rest ignored
        } catch (e: Exception) {
            return null
        }
        val items = when {
            data.isJsonObject -> data.asJsonObject["translations"]?.takeIf { it.isJsonArray }?.asJsonArray ?: return null
            data.isJsonArray -> data.asJsonArray
            else -> return null
        }
        if (items.size() != n) return null
        val out = items.map { if (it.isJsonPrimitive && it.asJsonPrimitive.isString) it.asString.trim() else return null }
        return if (out.all { it.isNotEmpty() }) out else null
    }
}
