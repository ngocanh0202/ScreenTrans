package dev.screentrans

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Foreground service that owns the MediaProjection for the whole session and the Controller
 * (bubble, capture, translation engine, result overlays).
 */
class CaptureService : Service() {
    private var projection: MediaProjection? = null
    private val main = Handler(Looper.getMainLooper())
    private var controller: Controller? = null

    private val projectionCallback = object : MediaProjection.Callback() {
        override fun onStop() {  // user revoked capture (status bar chip / Android 14+), or another app took it
            main.post { stopSelf() }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        val resultCode = intent?.getIntExtra(EXTRA_CODE, 0) ?: 0
        @Suppress("DEPRECATION")
        val data: Intent? = intent?.getParcelableExtra(EXTRA_DATA)
        if (projection == null && data != null) {
            val mpm = getSystemService(MediaProjectionManager::class.java)
            val p = mpm.getMediaProjection(resultCode, data)
            if (p == null) {
                stopSelf()
                return START_NOT_STICKY
            }
            p.registerCallback(projectionCallback, main)  // must precede createVirtualDisplay on Android 14+
            projection = p
            _running.value = true
            onProjectionReady(p)
        }
        return START_NOT_STICKY
    }

    private fun onProjectionReady(projection: MediaProjection) {
        controller = Controller(this, projection).also { it.start() }
        current = this
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        controller?.onRotated()  // rotation / resolution change: resize the capture surface
    }

    private fun startInForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "ScreenTrans", NotificationManager.IMPORTANCE_LOW))
        val stopIntent = PendingIntent.getService(
            this, 0, Intent(this, CaptureService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val openIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .setContentTitle("ScreenTrans đang chạy")
            .setContentText("Chạm nút nổi trong game để dịch.")
            .setContentIntent(openIntent)
            .addAction(Notification.Action.Builder(null, "Dừng", stopIntent).build())
            .setOngoing(true)
            .build()
        startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
    }

    override fun onDestroy() {
        if (current === this) current = null
        controller?.stop()
        controller = null
        projection?.unregisterCallback(projectionCallback)
        projection?.stop()
        projection = null
        _running.value = false
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL = "screentrans"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_STOP = "dev.screentrans.STOP"
        private const val EXTRA_CODE = "code"
        private const val EXTRA_DATA = "data"

        private val _running = MutableStateFlow(false)
        val running: StateFlow<Boolean> = _running

        fun start(context: Context, resultCode: Int, data: Intent) {
            val i = Intent(context, CaptureService::class.java).putExtra(EXTRA_CODE, resultCode).putExtra(EXTRA_DATA, data)
            context.startForegroundService(i)
        }

        @Volatile
        private var current: CaptureService? = null

        /** A setting changed on the app's start screen: the running session applies it (main thread). */
        fun settingsChanged(change: SettingsChange) {
            val s = current ?: return
            s.main.post { s.controller?.onSettingsChanged(change) }
        }

        fun stop(context: Context) {
            context.startService(Intent(context, CaptureService::class.java).setAction(ACTION_STOP))
        }
    }
}
