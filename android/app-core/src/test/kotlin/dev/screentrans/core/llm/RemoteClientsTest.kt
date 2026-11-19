package dev.screentrans.core.llm

import com.google.gson.JsonParser
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.jupiter.api.Test
import java.net.SocketTimeoutException
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Same cases as windows/tests/test_remote.py. */
class RemoteClientsTest {
    private val key = "sk-SECRET-123"
    private val reply = """{"translations": ["Chào."]}"""

    private class Fake(val status: Int = 200, val body: String = "", val error: Exception? = null) : HttpTransport {
        val requests = mutableListOf<Triple<String, Map<String, String>, String>>()
        val timeouts = mutableListOf<Int>()
        override fun post(url: String, headers: Map<String, String>, body: String, timeoutMs: Int): Pair<Int, ByteArray> {
            requests.add(Triple(url, headers, body))
            timeouts.add(timeoutMs)
            error?.let { throw it }
            return status to this.body.toByteArray()
        }
    }

    private fun gemini(text: String) = """{"candidates": [{"content": {"parts": [{"text": ${JsonParser.parseString("\"" + text.replace("\"", "\\\"") + "\"")}}]}}]}"""
    private fun openai(text: String) = """{"choices": [{"message": {"content": ${JsonParser.parseString("\"" + text.replace("\"", "\\\"") + "\"")}}}]}"""
    private val ok = mapOf("gemini" to gemini(reply), "openai" to openai(reply), "kaggle" to """{"translations": ["Chào."]}""")

    private fun client(engine: String, t: HttpTransport, k: String = key) =
        makeClient(engine, k, url = "https://abc.ngrok.app", transport = t)

    @Test
    fun `http clients return the reply text`() {
        for (engine in listOf("gemini", "openai", "kaggle")) {
            val t = Fake(body = ok.getValue(engine))
            val out = client(engine, t).complete("SYS", "Dịch các câu sau:\n[\"Hi.\"]", 6000)
            assertEquals(listOf("Chào."), JsonParser.parseString(out).asJsonObject["translations"].asJsonArray.map { it.asString })
            assertEquals(6000, t.timeouts[0])
        }
    }

    @Test
    fun `gemini request shape, no reasoning`() {
        val t = Fake(body = ok.getValue("gemini"))
        makeClient("gemini", key, transport = t).complete("SYS", "USER", 2500)
        val (url, headers, body) = t.requests[0]
        assertEquals("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent", url)
        assertEquals(key, headers["x-goog-api-key"])
        val b = JsonParser.parseString(body).asJsonObject
        assertEquals("SYS", b["systemInstruction"].asJsonObject["parts"].asJsonArray[0].asJsonObject["text"].asString)
        assertEquals("USER", b["contents"].asJsonArray[0].asJsonObject["parts"].asJsonArray[0].asJsonObject["text"].asString)
        val cfg = b["generationConfig"].asJsonObject
        assertEquals("application/json", cfg["responseMimeType"].asString)
        assertEquals(0, cfg["thinkingConfig"].asJsonObject["thinkingBudget"].asInt)
    }

    @Test
    fun `openai request shape and cleaned key`() {
        val t = Fake(body = ok.getValue("openai"))
        makeClient("openai", " sk-​ab\ncd  ", model = "my-model", transport = t).complete("SYS", "USER", 2500)
        val (url, headers, body) = t.requests[0]
        assertEquals("https://api.openai.com/v1/chat/completions", url)
        assertEquals("Bearer sk-abcd", headers["Authorization"])
        val b = JsonParser.parseString(body).asJsonObject
        assertEquals("my-model", b["model"].asString)
        assertEquals("minimal", b["reasoning_effort"].asString)
        assertEquals("json_object", b["response_format"].asJsonObject["type"].asString)
    }

    @Test
    fun `kaggle request carries the prompt, model id is the host`() {
        val t = Fake(body = ok.getValue("kaggle"))
        val c = makeClient("kaggle", "tok", url = "https://abc.ngrok-free.app/", transport = t)
        c.complete("SYS", "PROMPT", 6000)
        val (url, headers, body) = t.requests[0]
        assertEquals("https://abc.ngrok-free.app/translate", url)
        assertEquals("Bearer tok", headers["Authorization"])
        val b = JsonParser.parseString(body).asJsonObject
        assertEquals("SYS", b["system"].asString); assertEquals("PROMPT", b["prompt"].asString); assertEquals("en", b["source_lang"].asString)
        assertEquals("abc.ngrok-free.app", c.model)
    }

    @Test
    fun `http errors map to kinds and never show the key`() {
        val cases = mapOf(401 to "auth", 403 to "auth", 429 to "quota", 500 to "server", 503 to "server")
        for (engine in listOf("gemini", "openai", "kaggle")) for ((status, kind) in cases) {
            val e = assertFailsWith<RemoteError> { client(engine, Fake(status, """{"error": "bad key $key"}""")).complete("S", "U", 1000) }
            assertEquals(kind, e.kind, "$engine $status")
            assertFalse(key in (e.message ?: ""))
        }
    }

    @Test
    fun `gemini 400 with an invalid key is an auth error`() {
        val body = """{"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}"""
        assertEquals("auth", assertFailsWith<RemoteError> { client("gemini", Fake(400, body)).complete("S", "U", 1) }.kind)
        assertEquals("server", assertFailsWith<RemoteError> { client("gemini", Fake(400, """{"error": {"status": "INVALID_ARGUMENT"}}""")).complete("S", "U", 1) }.kind)
    }

    @Test
    fun `transport errors map to kinds without their text`() {
        val cases = listOf(SocketTimeoutException("timed out") to "timeout", java.io.IOException("no route $key") to "network",
            IllegalArgumentException("Unexpected char in header: Bearer $key") to "auth")
        for ((err, kind) in cases) {
            val e = assertFailsWith<RemoteError> { client("openai", Fake(error = err)).complete("S", "U", 1) }
            assertEquals(kind, e.kind)
            assertFalse(key in (e.message ?: ""))
            assertEquals(null, e.cause)
        }
    }

    @Test
    fun `garbage body is a bad reply`() {
        for (engine in listOf("gemini", "openai")) {
            assertEquals("bad_reply", assertFailsWith<RemoteError> { client(engine, Fake(body = "<html>oops</html>")).complete("S", "U", 1) }.kind)
        }
    }

    // ---- Claude (official SDK) against a local mock server ----------------------------------------------------
    private fun message(text: String, stop: String = "end_turn") = """{"id": "msg_1", "type": "message", "role": "assistant",
        "model": "claude-opus-5-5", "content": [{"type": "text", "text": ${com.google.gson.Gson().toJson(text)}}],
        "stop_reason": "$stop", "stop_sequence": null, "usage": {"input_tokens": 10, "output_tokens": 5}}"""

    @Test
    fun `claude request and reply`() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody(message(reply)).setHeader("Content-Type", "application/json"))
            val c = makeClient("claude", key, baseUrl = server.url("/").toString().trimEnd('/'))
            assertEquals("claude-opus-5-5", c.model)
            assertEquals(reply, c.complete("SYS", "USER", 6000))
            val req = server.takeRequest()
            assertTrue(req.path!!.startsWith("/v1/messages"))
            assertTrue(key == req.getHeader("x-api-key") || "Bearer $key" == req.getHeader("Authorization"))
            assertTrue("server-side-fallback-2026-07-01" in (req.getHeader("anthropic-beta") ?: ""))
            val b = JsonParser.parseString(req.body.readUtf8()).asJsonObject
            assertEquals("claude-opus-5-5", b["model"].asString)
            assertEquals("default", b["fallbacks"].asString)
            assertEquals("low", b["output_config"].asJsonObject["effort"].asString)
            assertEquals("json_schema", b["output_config"].asJsonObject["format"].asJsonObject["type"].asString)
        }
    }

    @Test
    fun `claude errors map to kinds`() {
        for ((status, kind) in mapOf(401 to "auth", 403 to "auth", 429 to "quota", 500 to "server", 529 to "server")) {
            MockWebServer().use { server ->
                server.enqueue(MockResponse().setResponseCode(status).setHeader("Content-Type", "application/json")
                    .setBody("""{"type": "error", "error": {"type": "x", "message": "bad $key"}}"""))
                val e = assertFailsWith<RemoteError> {
                    makeClient("claude", key, baseUrl = server.url("/").toString().trimEnd('/')).complete("S", "U", 3000)
                }
                assertEquals(kind, e.kind, "$status")
                assertFalse(key in (e.message ?: ""))
            }
        }
    }

    @Test
    fun `claude refusal is a bad reply`() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody(message("", stop = "refusal")).setHeader("Content-Type", "application/json"))
            val e = assertFailsWith<RemoteError> { makeClient("claude", key, baseUrl = server.url("/").toString().trimEnd('/')).complete("S", "U", 3000) }
            assertEquals("bad_reply", e.kind)
        }
    }
}
