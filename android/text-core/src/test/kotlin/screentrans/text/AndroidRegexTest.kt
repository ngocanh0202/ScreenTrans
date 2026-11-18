package screentrans.text

import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertEquals

/** Android's regex engine is ICU: inline flags other than i/d/m/s/u/w/x (e.g. "(?U") throw there. */
class AndroidRegexTest {
    @Test
    fun `no inline flags that ICU rejects`() {
        val bad = File("src/main/kotlin").walkTopDown().filter { it.extension == "kt" }
            .flatMap { f -> f.readLines().mapIndexedNotNull { i, l -> if ("(?U" in l) "${f.name}:${i + 1}" else null } }
            .toList()
        assertEquals(emptyList(), bad)
    }

    @Test
    fun `unicode whitespace still splits tokens like Python str split`() {
        assertEquals("a b c d", normalizeText("a b　c d"))
        assertEquals(listOf("x."), Postprocess.splitSentences("  x.  "))
    }

    @Test
    fun `glossary word boundaries still treat accented letters as word characters`() {
        val g = Glossary.load("""{"version": 1, "entries": [{"source": "HP", "type": "keep"}]}""")
        assertEquals(emptyList(), g.protect("éHP and HPé").second)
        assertEquals(listOf("HP"), g.protect("(HP)").second)
    }
}
