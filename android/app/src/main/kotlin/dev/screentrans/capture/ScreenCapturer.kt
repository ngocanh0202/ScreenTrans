package dev.screentrans.capture

import android.content.Context
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.DisplayMetrics
import android.view.WindowManager
import dev.screentrans.core.live.Thumb
import kotlinx.coroutines.delay

/**
 * One VirtualDisplay for the whole MediaProjection session (Android 14+ allows only one per token).
 * The newest frame is held (not converted) as frames arrive, so idle cost stays low; [capture]
 * converts it to a Bitmap on demand.
 */
class ScreenCapturer(private val projection: MediaProjection, private val context: Context) {
    private val thread = HandlerThread("screentrans-capture").apply { start() }
    private val handler = Handler(thread.looper)
    private val lock = Any()
    private var reader: ImageReader? = null
    private var display: VirtualDisplay? = null
    private var latest: Image? = null
    private var latestAt = 0L  // SystemClock.uptimeMillis() when the held frame arrived

    /** Uptime ms when the held frame arrived (0 = none yet). */
    val lastFrameAt: Long get() = synchronized(lock) { latestAt }

    var width = 0
        private set
    var height = 0
        private set

    init {
        val (w, h, dpi) = screenSize()
        width = w
        height = h
        val r = newReader(w, h)
        reader = r
        display = projection.createVirtualDisplay(
            "screentrans", w, h, dpi, DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, r.surface, null, handler,
        )
    }

    private fun screenSize(): Triple<Int, Int, Int> {
        val wm = context.getSystemService(WindowManager::class.java)
        val dpi = context.resources.displayMetrics.densityDpi
        return if (Build.VERSION.SDK_INT >= 30) {
            val b = wm.currentWindowMetrics.bounds
            Triple(b.width(), b.height(), dpi)
        } else {
            val m = DisplayMetrics()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealMetrics(m)
            Triple(m.widthPixels, m.heightPixels, dpi)
        }
    }

    private fun newReader(w: Int, h: Int): ImageReader =
        ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 2).apply {
            setOnImageAvailableListener({ r ->
                val img = r.acquireLatestImage() ?: return@setOnImageAvailableListener
                synchronized(lock) {
                    // a frame of the reader that resize() just replaced: closing that reader closes its images,
                    // so never keep one as the latest frame (reading its planes would throw)
                    if (r !== reader) {
                        img.close()
                        return@setOnImageAvailableListener
                    }
                    latest?.close()
                    latest = img
                    latestAt = SystemClock.uptimeMillis()
                }
            }, handler)
        }

    /** Call after a rotation / resolution change: resize the existing display and swap the reader. */
    fun resize() {
        val (w, h, dpi) = screenSize()
        if (w == width && h == height) return
        val old = reader
        val r = newReader(w, h)
        synchronized(lock) {
            latest?.close()
            latest = null
            width = w
            height = h
            reader = r
        }
        display?.resize(w, h, dpi)
        display?.surface = r.surface
        old?.close()
    }

    /**
     * Newest frame as a Bitmap. With [newerThan] (uptime ms) wait up to [timeoutMs] for a frame that
     * arrived after it (e.g. after our overlays were hidden), then fall back to the newest one.
     */
    suspend fun capture(newerThan: Long = 0L, timeoutMs: Long = 400L): Bitmap? {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            if (synchronized(lock) { latest != null && latestAt > newerThan }) break
            delay(16)
        }
        return synchronized(lock) { latest?.let { toBitmap(it) } }
    }

    /**
     * Gray thumbnail ([Thumb.fromArgb], [width] px wide) of rect (l, t, r, b) read straight from the
     * held frame — no full-screen Bitmap per Live tick. Null when there is no frame or the rect is empty.
     */
    fun thumbnail(rect: IntArray, width: Int = Thumb.WIDTH): FloatArray? = synchronized(lock) { thumbLocked(rect, width) }

    private fun thumbLocked(rect: IntArray, width: Int): FloatArray? {
        val img = latest ?: return null
        val l = rect[0].coerceIn(0, img.width)
        val t = rect[1].coerceIn(0, img.height)
        val r = rect[2].coerceIn(0, img.width)
        val b = rect[3].coerceIn(0, img.height)
        if (r - l < 2 || b - t < 2) return null
        val plane = img.planes[0]
        val buf = plane.buffer
        val ps = plane.pixelStride
        val rs = plane.rowStride
        val step = maxOf(1, (r - l) / (width * 4))  // ~4 samples per thumbnail pixel per axis is plenty
        val sw = (r - l + step - 1) / step
        val sh = (b - t + step - 1) / step
        val px = IntArray(sw * sh)
        for (j in 0 until sh) {
            val row = (t + j * step) * rs
            for (i in 0 until sw) {
                val o = row + (l + i * step) * ps  // RGBA_8888
                val red = buf.get(o).toInt() and 0xFF
                val green = buf.get(o + 1).toInt() and 0xFF
                val blue = buf.get(o + 2).toInt() and 0xFF
                px[j * sw + i] = (0xFF shl 24) or (red shl 16) or (green shl 8) or blue
            }
        }
        return Thumb.fromArgb(px, sw, sh, width)
    }

    private fun toBitmap(image: Image): Bitmap {
        val plane = image.planes[0]
        val buffer = plane.buffer.apply { rewind() }
        val pixelStride = plane.pixelStride
        val rowPadding = plane.rowStride - pixelStride * image.width
        val padded = Bitmap.createBitmap(image.width + rowPadding / pixelStride, image.height, Bitmap.Config.ARGB_8888)
        padded.copyPixelsFromBuffer(buffer)
        if (rowPadding == 0) return padded
        return Bitmap.createBitmap(padded, 0, 0, image.width, image.height).also { padded.recycle() }
    }

    fun release() {
        synchronized(lock) {
            latest?.close()
            latest = null
        }
        display?.release()
        display = null
        reader?.close()
        reader = null
        thread.quitSafely()
    }
}
