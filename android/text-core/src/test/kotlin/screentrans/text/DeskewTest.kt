package screentrans.text

import org.junit.jupiter.api.Test
import kotlin.math.hypot
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class DeskewTest {
    private fun corners(cx: Float, cy: Float, w: Float, h: Float, angle: Float): List<Pair<Float, Float>> {
        val (dcx, dcy) = Deskew.rotate(cx, cy, angle)
        return listOf(dcx - w / 2 to dcy - h / 2, dcx + w / 2 to dcy - h / 2, dcx + w / 2 to dcy + h / 2, dcx - w / 2 to dcy + h / 2)
            .map { (x, y) -> Deskew.unrotate(x, y, angle) }
    }

    @Test
    fun `rotate and unrotate are inverse`() {
        val (x, y) = Deskew.rotate(123f, 45f, 17f).let { (a, b) -> Deskew.unrotate(a, b, 17f) }
        assertEquals(123f, x, 0.01f); assertEquals(45f, y, 0.01f)
    }

    @Test
    fun `from corners gives back the straight box`() {
        val box = Deskew.fromCorners(corners(300f, 200f, 200f, 30f, 15f), 15f)
        assertEquals(200f, box[2], 0.05f); assertEquals(30f, box[3], 0.05f)
        val (dcx, dcy) = Deskew.rotate(300f, 200f, 15f)
        assertEquals(dcx, box[0] + box[2] / 2, 0.05f); assertEquals(dcy, box[1] + box[3] / 2, 0.05f)
    }

    @Test
    fun `bounds of a tilted box contains its corners`() {
        val b = Deskew.bounds(floatArrayOf(100f, 200f, 300f, 230f), 20f)
        for ((x, y) in listOf(100f to 200f, 300f to 200f, 300f to 230f, 100f to 230f)) {
            val (sx, sy) = Deskew.unrotate(x, y, 20f)
            assertTrue(sx >= b[0] - 0.01f && sx <= b[2] + 0.01f && sy >= b[1] - 0.01f && sy <= b[3] + 0.01f)
        }
        assertTrue(hypot(1f, 1f) > 0)
    }
}
