package dev.screentrans

import android.content.Context
import android.os.SystemClock
import android.view.View
import android.widget.Toast
import dev.screentrans.core.Layout
import dev.screentrans.core.model.ManifestModel
import dev.screentrans.core.model.ModelCatalog
import dev.screentrans.core.model.ModelRow
import dev.screentrans.engine.AppEngine
import dev.screentrans.engine.KeyVault
import dev.screentrans.profile.ProfileRepo
import dev.screentrans.ui.LlmPanel
import dev.screentrans.ui.LlmValues
import dev.screentrans.ui.ModelsPanel
import dev.screentrans.ui.PanelTile
import dev.screentrans.ui.Prefs
import dev.screentrans.ui.SettingsPanel
import dev.screentrans.ui.SettingsValues
import dev.screentrans.ui.TermsPanel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import screentrans.text.TermEdit
import java.io.File

/** What a settings change needs from the running app (engine / Live). */
enum class SettingsChange { STYLE, GAME, MODEL }

/** Where the settings screens are shown: the floating overlays (Controller) or the app's own screen (MainActivity). */
interface SettingsHost {
    /** Show [panel] instead of what this host shows now; [focusable]: it has text fields (keyboard). */
    fun present(panel: View, focusable: Boolean)

    fun dismiss()

    /** The game the settings are for. */
    fun gameId(): String

    /** A change was saved: apply it to the running engine / Live. */
    fun changed(change: SettingsChange)
}

/**
 * The ⚙ settings and its screens (🌐 Dịch bằng, 📖 Thuật ngữ, 🧠 Model), the same in the floating panel and on the
 * app's start screen: this class saves, the [host] shows the panels and applies the changes.
 */
class SettingsScreens(private val context: Context, private val scope: CoroutineScope, private val host: SettingsHost) {
    private val prefs = Prefs(context)
    private val repo = ProfileRepo(context)
    private val keyVault by lazy { KeyVault(context) }
    private val modelStore by lazy { AppEngine.store(context) }
    private var modelsPanel: ModelsPanel? = null
    private var manifest: List<ManifestModel>? = null
    private var modelBusy: String? = null

    fun profile(id: String = host.gameId()) = repo.getOrDefault(id, repo.label(id))

    fun values() = SettingsValues(
        readable = profile().style == "classic", textScale = prefs.textScale,
        growLong = prefs.longText != "shrink", game = repo.label(host.gameId()),
    )

    /** The ⚙ panel: style, text size, long translations, OCR, then [tools] (the host's) and this class's screens. */
    fun settingsPanel(tools: List<PanelTile>, onClose: (() -> Unit)?): SettingsPanel {
        lateinit var panel: SettingsPanel
        panel = SettingsPanel(
            context, values(),
            onReadable = { readable ->
                repo.save(profile().copy(style = if (readable) "classic" else "match"))
                host.changed(SettingsChange.STYLE)
                panel.render(values())
            },
            onScale = { up ->
                prefs.textScale = if (up) Layout.nextScale(prefs.textScale) else Layout.prevScale(prefs.textScale)
                host.changed(SettingsChange.STYLE)
                panel.render(values())
            },
            onGrowLong = { growLong ->
                prefs.longText = if (growLong) "grow" else "shrink"
                host.changed(SettingsChange.STYLE)
                panel.render(values())
            },
            tools = tools + tiles(),
            onClose = onClose,
        )
        return panel
    }

    /** The on-device model in use, shortly ("opus-mt", "ScreenTrans", or a downloaded model's id). */
    fun localModelName(): String = when (prefs.modelId) {
        AppEngine.MODEL_ID -> "opus-mt"
        "screentrans-en-vi" -> "ScreenTrans"
        else -> prefs.modelId
    }

    fun tiles() = listOf(
        PanelTile("🌐", "Dịch bằng: ${dev.screentrans.core.llm.NAMES[profile().engine] ?: "máy (${localModelName()})"}", ::showLlm),
        PanelTile("📖", "Thuật ngữ", ::showTerms),
        PanelTile("🧠", "Model: ${localModelName()}", ::showModels),
    )

    /** 🌐 Dịch bằng: the game's engine (on-device or a remote LLM), key, model, limit, notes. */
    fun showLlm() {
        val p = profile()
        val values = LlmValues(
            game = repo.label(p.id), engine = p.engine,
            savedKeys = dev.screentrans.core.llm.NAMES.keys.filter { keyVault.has(it) }.toSet(),
            models = prefs.llmModels, liveModels = prefs.llmLiveModels, kaggleUrl = prefs.kaggleUrl, dailyLimit = prefs.dailyLimit,
            usedToday = dev.screentrans.core.llm.UsageStore(File(context.filesDir, "llm")).used(),
            notes = p.llmNotes, localModel = localModelName(),
        )
        host.present(LlmPanel(context, values, onSave = { e ->
            if (e.deleteKey) keyVault.set(e.engine, "")
            e.key?.let {  // encrypted (Android Keystore), never in prefs or logs
                if (!keyVault.set(e.engine, it)) Toast.makeText(context, "Không lưu được key (Keystore lỗi).", Toast.LENGTH_LONG).show()
            }
            if (e.engine in dev.screentrans.core.llm.NAMES) {
                prefs.llmModels = dev.screentrans.core.ui.LlmPrefsLogic.models(prefs.llmModels, e.engine, e.model)
                prefs.llmLiveModels = dev.screentrans.core.ui.LlmPrefsLogic.liveModels(prefs.llmLiveModels, e.engine, e.liveModel, prefs.llmModels)
            }
            if (e.engine == "kaggle") prefs.kaggleUrl = e.kaggleUrl
            prefs.dailyLimit = e.dailyLimit
            repo.save(profile(p.id).copy(engine = e.engine, llmNotes = e.notes))  // the game the panel showed
            host.changed(SettingsChange.GAME)  // send the game (with its engine) to the engine again
            host.dismiss()
        }, onClose = host::dismiss), focusable = true)
    }

    /** 📖 Thuật ngữ: the game's own glossary terms; saved to its file and sent to the engine at once. */
    fun showTerms() {
        val id = host.gameId()
        val file = repo.userGlossary(id)
        var rows = emptyList<TermEdit.Row>()
        if (file.isFile) {
            val parsed = runCatching { TermEdit.parse(file.readText()) }.getOrNull()
            if (parsed == null) {  // keep the broken file for the user, start a new one
                file.renameTo(File(file.path + ".bad"))
                Toast.makeText(context, "File thuật ngữ hỏng, đã đổi tên thành ${file.name}.bad.", Toast.LENGTH_LONG).show()
            } else rows = parsed
        }
        host.present(TermsPanel(context, repo.label(id), rows, onSave = { edited ->
            repo.saveTerms(id, edited)
            host.changed(SettingsChange.GAME)  // reload the game's glossaries in the engine
            host.dismiss()
        }, onClose = host::dismiss), focusable = true)
    }

    // ---- models ---------------------------------------------------------------------------------
    private fun modelRows(): List<ModelRow> {
        // the bundled model is updated with the app: never shown as "Có bản mới"
        val bundledVersion = manifest?.firstOrNull { it.id == AppEngine.MODEL_ID }?.version ?: "app"
        return ModelCatalog.rows(manifest.orEmpty(), modelStore.installed(), mapOf(AppEngine.MODEL_ID to bundledVersion), prefs.modelId)
    }

    private fun renderModels(message: String) {
        modelsPanel?.render(modelRows(), modelBusy, message)
    }

    /** 🧠 Model: the published models (Hugging Face) and the downloaded ones; download / use / delete. */
    fun showModels() {
        val panel = ModelsPanel(context,
            onDownload = { r -> downloadModel(r, use = false) },
            onUse = { r -> if (r.status == "missing") downloadModel(r, use = true) else useModel(r) },
            onDelete = { r ->
                modelStore.delete(r.id)
                renderModels("Đã xóa ${r.label}.")
            },
            onClose = host::dismiss)
        modelsPanel = panel
        host.present(panel, focusable = false)
        renderModels("Đang đọc danh sách model…")
        scope.launch {
            val m = withContext(Dispatchers.IO) { runCatching { modelStore.manifest() }.getOrNull() }
            if (m != null) manifest = m
            renderModels(if (m == null) "Không đọc được danh sách model trên mạng: chỉ hiện model trên máy."
                else "Model tải về nằm trong bộ nhớ của app. Đang tải thì vẫn đóng bảng này được.")
        }
    }

    private fun downloadModel(r: ModelRow, use: Boolean) {
        val m = manifest?.firstOrNull { it.id == r.id } ?: return
        if (modelBusy != null) return
        modelBusy = r.id
        renderModels("Đang tải ${r.label}…")
        scope.launch {
            var shownAt = 0L
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    modelStore.download(m) { done, total ->
                        val now = SystemClock.uptimeMillis()
                        if (now - shownAt > 300) {
                            shownAt = now
                            scope.launch { renderModels("Đang tải ${r.label}: ${done * 100 / maxOf(total, 1L)}%") }
                        }
                    }
                }
            }
            modelBusy = null
            result.fold(
                onSuccess = { if (use) useModel(r) else renderModels("Đã tải ${r.label}.") },
                onFailure = { renderModels("Không tải được: ${it.message}") },
            )
        }
    }

    private fun useModel(r: ModelRow) {
        prefs.modelId = r.id
        host.changed(SettingsChange.MODEL)  // the old model keeps translating until the new one is loaded
        renderModels("Đang chuyển sang ${r.label}…")
    }
}
