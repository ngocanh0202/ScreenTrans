package dev.screentrans.core.llm

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import screentrans.text.LlmPrompt
import java.io.IOException
import java.io.InterruptedIOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URI
import java.net.URL

/**
 * Remote LLM clients (Phase 5): Gemini / OpenAI / Kaggle over HttpURLConnection, Claude through the official SDK.
 * Same behaviour as windows/app/translate/remote.py: the reply text, or a [RemoteError] whose message never
 * holds the key or the request.
 */
class RemoteError(val kind: String, provider: String, detail: String = "") :
    Exception("$provider: $kind" + if (detail.isNotEmpty()) " ($detail)" else "")

interface LlmClient {
    val name: String
    val model: String
    fun complete(system: String, user: String, timeoutMs: Int): String
}

/** POST [body] (JSON) to [url]: (status, response bytes). Throws IOException / SocketTimeoutException. */
fun interface HttpTransport {
    fun post(url: String, headers: Map<String, String>, body: String, timeoutMs: Int): Pair<Int, ByteArray>
}

object UrlConnectionTransport : HttpTransport {
    override fun post(url: String, headers: Map<String, String>, body: String, timeoutMs: Int): Pair<Int, ByteArray> {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"
            c.connectTimeout = timeoutMs
            c.readTimeout = timeoutMs
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            headers.forEach { (k, v) -> c.setRequestProperty(k, v) }
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val status = c.responseCode
            val stream = if (status >= 400) c.errorStream else c.inputStream
            return status to (stream?.use { it.readBytes() } ?: ByteArray(0))
        } finally {
            c.disconnect()
        }
    }
}

val NAMES = mapOf("gemini" to "Gemini", "openai" to "OpenAI", "claude" to "Claude", "kaggle" to "Kaggle")
/** Shown as suggestions in "🌐 Dịch bằng"; any other model name of the provider can be typed. */
val SUGGESTED_MODELS = mapOf(
    "gemini" to listOf("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"),
    "openai" to listOf("gpt-5-mini", "gpt-5-nano", "gpt-5"),
    "claude" to listOf("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
    "kaggle" to emptyList(),
)
val DEFAULT_MODELS = mapOf("gemini" to "gemini-2.5-flash", "openai" to "gpt-5-mini", "claude" to "claude-opus-5-5", "kaggle" to "server")
private const val MAX_TOKENS = 4096L

private fun kindForStatus(status: Int) = when (status) {
    401, 403 -> "auth"
    429 -> "quota"
    408 -> "timeout"
    else -> "server"
}

private abstract class HttpClient(protected val key: String, override val model: String, private val transport: HttpTransport) : LlmClient {
    protected val gson = Gson()

    /** A provider that reports a wrong key with another status (the body is never shown). */
    protected open fun authHint(status: Int, body: ByteArray): String? = null

    protected fun post(url: String, headers: Map<String, String>, body: JsonObject, timeoutMs: Int): JsonObject {
        val (status, raw) = try {
            transport.post(url, headers, gson.toJson(body), timeoutMs)
        } catch (e: SocketTimeoutException) {
            throw RemoteError("timeout", name)
        } catch (e: InterruptedIOException) {
            throw RemoteError("timeout", name)
        } catch (e: IOException) {
            throw RemoteError("network", name)
        } catch (e: IllegalArgumentException) {  // the key cannot go in a header: a broken key (its text would show it)
            throw RemoteError("auth", name)
        }
        if (status >= 400) {
            val kind = kindForStatus(status).let { if (it == "server") authHint(status, raw) ?: it else it }
            throw RemoteError(kind, name, "HTTP $status")
        }
        return try {
            JsonParser.parseString(String(raw, Charsets.UTF_8)).asJsonObject
        } catch (e: Exception) {
            throw RemoteError("bad_reply", name)
        }
    }

    protected fun pick(data: JsonObject, vararg path: Any): String {
        var cur: com.google.gson.JsonElement = data
        try {
            for (p in path) cur = if (p is Int) cur.asJsonArray[p] else cur.asJsonObject[p as String]
            if (cur.isJsonPrimitive && cur.asJsonPrimitive.isString) return cur.asString
        } catch (e: Exception) {
            // falls through
        }
        throw RemoteError("bad_reply", name)
    }
}

private class GeminiClient(key: String, model: String, t: HttpTransport) : HttpClient(key, model, t) {
    override val name = "Gemini"
    override fun authHint(status: Int, body: ByteArray): String? {
        val text = String(body, Charsets.UTF_8)
        return if (status == 400 && ("API_KEY_INVALID" in text || "API key not valid" in text)) "auth" else null
    }

    override fun complete(system: String, user: String, timeoutMs: Int): String {
        val body = JsonParser.parseString(gson.toJson(mapOf(
            "systemInstruction" to mapOf("parts" to listOf(mapOf("text" to system))),
            "contents" to listOf(mapOf("role" to "user", "parts" to listOf(mapOf("text" to user)))),
            "generationConfig" to mapOf("responseMimeType" to "application/json",
                "thinkingConfig" to mapOf("thinkingBudget" to 0)),  // translation: no reasoning, fast
        ))).asJsonObject
        val data = post("https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent",
            mapOf("x-goog-api-key" to key), body, timeoutMs)
        return pick(data, "candidates", 0, "content", "parts", 0, "text")
    }
}

private class OpenAiClient(key: String, model: String, t: HttpTransport) : HttpClient(key, model, t) {
    override val name = "OpenAI"
    override fun complete(system: String, user: String, timeoutMs: Int): String {
        val body = JsonParser.parseString(gson.toJson(mapOf(
            "model" to model, "response_format" to mapOf("type" to "json_object"), "reasoning_effort" to "minimal",
            "messages" to listOf(mapOf("role" to "system", "content" to system), mapOf("role" to "user", "content" to user)),
        ))).asJsonObject
        val data = post("https://api.openai.com/v1/chat/completions", mapOf("Authorization" to "Bearer $key"), body, timeoutMs)
        return pick(data, "choices", 0, "message", "content")
    }
}

/** Our own server (training/kaggle_serve.ipynb): it gets the built prompt, answers {"translations": [...]}. */
private class KaggleClient(key: String, model: String, private val url: String, t: HttpTransport) : HttpClient(key, model, t) {
    override val name = "Kaggle"
    override fun complete(system: String, user: String, timeoutMs: Int): String {
        if (url.isEmpty()) throw RemoteError("network", name, "chưa có URL server")
        val body = JsonParser.parseString(gson.toJson(mapOf("system" to system, "prompt" to user, "source_lang" to "en"))).asJsonObject
        val data = post("$url/translate", mapOf("Authorization" to "Bearer $key"), body, timeoutMs)
        val items = data["translations"]?.takeIf { it.isJsonArray } ?: throw RemoteError("bad_reply", name)
        return gson.toJson(mapOf("translations" to items))
    }
}

private class ClaudeClient(key: String, override val model: String, baseUrl: String?) : LlmClient {
    override val name = "Claude"
    private val client = com.anthropic.client.okhttp.AnthropicOkHttpClient.builder()
        .apiKey(key)
        .maxRetries(0)  // our own fallback handles failures
        .apply { if (baseUrl != null) baseUrl(baseUrl) }
        .build()

    override fun complete(system: String, user: String, timeoutMs: Int): String {
        val schema = com.anthropic.core.JsonValue.from(Gson().fromJson(LlmPrompt.REPLY_SCHEMA_JSON, Map::class.java))
        val params = com.anthropic.models.messages.MessageCreateParams.builder()
            .model(model)
            .maxTokens(MAX_TOKENS)
            .system(system)
            .addUserMessage(user)
            .putAdditionalHeader("anthropic-beta", "server-side-fallback-2026-07-01")
            .putAdditionalBodyProperty("fallbacks", com.anthropic.core.JsonValue.from("default"))
            .putAdditionalBodyProperty("output_config", com.anthropic.core.JsonValue.from(mapOf(
                "effort" to "low", "format" to mapOf("type" to "json_schema", "schema" to schema))))
            .build()
        val options = com.anthropic.core.RequestOptions.builder().timeout(java.time.Duration.ofMillis(timeoutMs.toLong())).build()
        val msg = try {
            client.messages().create(params, options)
        } catch (e: com.anthropic.errors.UnauthorizedException) {
            throw RemoteError("auth", name)
        } catch (e: com.anthropic.errors.PermissionDeniedException) {
            throw RemoteError("auth", name)
        } catch (e: com.anthropic.errors.RateLimitException) {
            throw RemoteError("quota", name)
        } catch (e: com.anthropic.errors.AnthropicServiceException) {
            throw RemoteError(kindForStatus(e.statusCode()), name, "HTTP ${e.statusCode()}")
        } catch (e: com.anthropic.errors.AnthropicIoException) {
            throw RemoteError(if (generateSequence(e as Throwable) { it.cause }.any { it is InterruptedIOException }) "timeout" else "network", name)
        } catch (e: Exception) {  // a key OkHttp cannot put in a header is a broken key (its text would show it)
            val badKey = generateSequence(e as Throwable) { it.cause }.any { it is IllegalArgumentException }
            throw RemoteError(if (badKey) "auth" else "server", name)
        }
        val stop = msg.stopReason().map { it.toString() }.orElse("")
        if (stop == "refusal" || stop == "max_tokens") throw RemoteError("bad_reply", name, stop)
        return msg.content().firstNotNullOfOrNull { b -> b.text().map { it.text() }.orElse(null) }
            ?: throw RemoteError("bad_reply", name)
    }
}

/** Keys never contain whitespace or zero-width characters; a pasted one often does. */
fun cleanKey(key: String): String = key.filter { !it.isWhitespace() && it !in " ​‌‍⁠﻿" }

fun makeClient(engine: String, key: String, model: String = "", url: String = "",
               transport: HttpTransport = UrlConnectionTransport, baseUrl: String? = null): LlmClient {
    val k = cleanKey(key)
    val m = model.trim().ifEmpty { DEFAULT_MODELS[engine] ?: "" }
    return when (engine) {
        "gemini" -> GeminiClient(k, m, transport)
        "openai" -> OpenAiClient(k, m, transport)
        "kaggle" -> {  // the server's host names it: each server gets its own cache namespace
            val u = url.trim().trimEnd('/')
            val host = runCatching { URI(u).let { if (it.port > 0) "${it.host}:${it.port}" else it.host } }.getOrNull()
                ?.takeIf { it.isNotEmpty() } ?: "server"  // host[:port], like Python netloc
            KaggleClient(k, host, u, transport)
        }
        "claude" -> ClaudeClient(k, m, baseUrl)
        else -> throw IllegalArgumentException("not a remote engine: $engine")
    }
}
