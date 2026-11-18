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
