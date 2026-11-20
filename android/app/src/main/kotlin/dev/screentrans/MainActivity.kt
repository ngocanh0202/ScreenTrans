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
import android.widget.LinearLayout
import android.widget.TextView
import android.app.Dialog
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.view.Window
import dev.screentrans.core.Step
import dev.screentrans.core.nextStep
import dev.screentrans.core.profile.ProfileLogic
import dev.screentrans.ui.SettingsPanel
import dev.screentrans.ui.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

/**
 * Start screen: walks the user through the permissions, then starts CaptureService. Below the buttons: the same
 * ⚙ settings as the floating panel (its 🌐 / 📖 / 🧠 screens open as dialogs; a running session applies changes).
 */
class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var action: TextView
    private lateinit var stop: TextView
    private lateinit var settings: SettingsPanel
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var dialog: Dialog? = null

    private val host: SettingsHost = object : SettingsHost {
        override fun present(panel: View, focusable: Boolean) {
            dialog?.dismiss()
            dialog = Dialog(this@MainActivity).apply {
                requestWindowFeature(Window.FEATURE_NO_TITLE)
                setContentView(panel)
                window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                val m = resources.displayMetrics
                window?.setLayout((m.widthPixels * 0.95f).toInt(), (m.heightPixels * 0.85f).toInt())
                show()
            }
        }

        override fun dismiss() {
            dialog?.dismiss()
            dialog = null
            settings.render(screens.values())
        }

        override fun gameId(): String =
            ProfileLogic.pickGame(null, dev.screentrans.ui.Prefs(this@MainActivity).manualGame, packageName)

        override fun changed(change: SettingsChange) = CaptureService.settingsChanged(change)
    }
    private val screens: SettingsScreens by lazy { SettingsScreens(this, scope, host) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { textSize = 15f; setPadding(0, 0, 0, dp(16)) }
        action = pill { onAction() }
        stop = pill { CaptureService.stop(this@MainActivity); refresh() }.apply {
            text = "■  Dừng ScreenTrans"
            paint(this, red)
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
            addView(TextView(context).apply {
                text = "🌐  ScreenTrans"; textSize = 26f; typeface = Typeface.DEFAULT_BOLD; setPadding(0, 0, 0, dp(12))
            })
            addView(status, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(action, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { bottomMargin = dp(8) })
            addView(stop, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            settings = screens.settingsPanel(emptyList(), onClose = null)
            addView(settings, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f).apply { topMargin = context.dp(16) })
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
        settings.render(screens.values())  // changed in the floating panel meanwhile
    }

    override fun onDestroy() {
        dialog?.dismiss()
        scope.cancel()
        super.onDestroy()
    }

    private val green = Color.rgb(22, 163, 74)
    private val red = Color.rgb(220, 38, 38)
    private val blue = Color.rgb(37, 99, 235)
    private val idle = Color.argb(60, 128, 128, 140)

    private fun dp(v: Int) = (this as android.content.Context).dp(v)

    /** A full-width rounded button: an icon and a label in one text. */
    private fun pill(action: () -> Unit) = TextView(this).apply {
        textSize = 17f
        typeface = Typeface.DEFAULT_BOLD
        gravity = android.view.Gravity.CENTER
        setTextColor(Color.WHITE)
        setPadding(dp(16), dp(14), dp(16), dp(14))
        background = GradientDrawable().apply { cornerRadius = dp(14).toFloat() }
        setOnClickListener { if (isEnabled) action() }
    }

    private fun paint(v: TextView, color: Int) {
        (v.background as GradientDrawable).setColor(color)
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
            Step.OVERLAY -> "🔓  Cho phép hiện trên ứng dụng khác"
            Step.NOTIFICATIONS -> "🔔  Cho phép thông báo"
            Step.CAPTURE -> "▶  Bắt đầu"
            Step.RUNNING -> "✔  Đang chạy"
        }
        paint(action, when (s) {  // the start button stands out; once running it steps back for the red stop
            Step.CAPTURE -> green
            Step.RUNNING -> idle
            else -> blue
        })
        action.isEnabled = s != Step.RUNNING
        stop.visibility = if (s == Step.RUNNING) View.VISIBLE else View.GONE
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
