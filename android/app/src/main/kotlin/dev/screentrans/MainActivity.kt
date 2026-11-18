package dev.screentrans

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowInsets
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import dev.screentrans.core.Step
import dev.screentrans.core.nextStep

/** Start screen: walks the user through the permissions, then starts CaptureService. */
class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var action: Button
    private lateinit var stop: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { textSize = 16f; setPadding(0, 0, 0, 32) }
        action = Button(this).apply { setOnClickListener { onAction() } }
        stop = Button(this).apply {
            text = "Dừng ScreenTrans"
            setOnClickListener { CaptureService.stop(this@MainActivity); refresh() }
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
            addView(TextView(context).apply { text = "ScreenTrans"; textSize = 26f; setPadding(0, 0, 0, 24) })
            addView(status, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(action, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(stop, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        }
        root.setOnApplyWindowInsetsListener { v, insets ->  // targetSdk 35+ draws edge-to-edge
            if (Build.VERSION.SDK_INT >= 30) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                v.setPadding(48 + bars.left, 48 + bars.top, 48 + bars.right, 48 + bars.bottom)
            }
            insets
        }
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun notificationsOk(): Boolean =
        Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private val prefs by lazy { getSharedPreferences("screentrans", MODE_PRIVATE) }

    private fun step() = nextStep(
        Settings.canDrawOverlays(this), notificationsOk(), CaptureService.running.value,
        notificationsAsked = prefs.getBoolean("notifications_asked", false),
    )

    private fun refresh() {
        val s = step()
        status.text = when (s) {
            Step.OVERLAY -> "1/3 — Cho phép ScreenTrans hiện trên ứng dụng khác (để vẽ nút nổi và bản dịch)."
            Step.NOTIFICATIONS -> "2/3 — Cho phép thông báo (để hiện nút Dừng khi đang chạy)."
            Step.CAPTURE -> "3/3 — Bấm Bắt đầu. Khi Android hỏi quyền ghi màn hình, chọn \"Một ứng dụng\" rồi chọn " +
                "game (bản dịch Live đè lên chữ mà không nháy). Chọn \"Toàn bộ màn hình\" cũng được, nhưng Live sẽ nháy nhẹ."
            Step.RUNNING -> "Đang chạy. Mở game, chạm nút nổi để dịch."
        }
        action.text = when (s) {
            Step.OVERLAY -> "Mở cài đặt quyền hiện trên ứng dụng khác"
            Step.NOTIFICATIONS -> "Cho phép thông báo"
            Step.CAPTURE -> "Bắt đầu"
            Step.RUNNING -> "Đang chạy"
        }
        action.isEnabled = s != Step.RUNNING
        stop.visibility = if (s == Step.RUNNING) Button.VISIBLE else Button.GONE
    }

    private fun onAction() {
        when (step()) {
            Step.OVERLAY -> startActivity(
                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))
            )
            Step.NOTIFICATIONS -> if (Build.VERSION.SDK_INT >= 33) {
                prefs.edit().putBoolean("notifications_asked", true).apply()  // denied twice -> no dialog: let them go on
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFY)
            }
            Step.CAPTURE -> {
                val mpm = getSystemService(MediaProjectionManager::class.java)
                @Suppress("DEPRECATION")
                startActivityForResult(mpm.createScreenCaptureIntent(), REQ_CAPTURE)
            }
            Step.RUNNING -> Unit
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        refresh()
    }

    @Deprecated("Activity result API is not used to keep the app free of androidx")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_CAPTURE && resultCode == RESULT_OK && data != null) {
            CaptureService.start(this, resultCode, data)
            moveTaskToBack(true)  // back to the game; the bubble is on screen now
        }
        refresh()
    }

    private companion object {
        const val REQ_NOTIFY = 1
        const val REQ_CAPTURE = 2
    }
}
