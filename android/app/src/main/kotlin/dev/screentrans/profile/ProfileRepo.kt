package dev.screentrans.profile

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context

import android.os.Process
import dev.screentrans.core.profile.Profile
import dev.screentrans.core.profile.ProfileLogic
import dev.screentrans.ui.Prefs
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** One JSON file per game in filesDir/profiles (same format as Windows, shared/fixtures/profiles). */
class ProfileRepo(private val context: Context) {
    private val dir = File(context.filesDir, "profiles")

    private fun file(id: String) = File(dir, id.map { if (it.isLetterOrDigit() || it in "._-") it else '_' }.joinToString("") + ".json")

    fun get(id: String): Profile? {
        val f = file(id)
        if (!f.isFile) return null
        val p = Profile.parse(f.readText())
        if (p == null) f.renameTo(File(f.path + ".bad"))  // keep it for the user, start over with defaults
        return p
    }

    fun getOrDefault(id: String, name: String = ""): Profile = get(id) ?: Profile(id, name)

    fun save(p: Profile) {
        dir.mkdirs()
        val f = file(p.id)
        val tmp = File(f.path + ".tmp")
        tmp.writeText(p.serialize())
        if (!tmp.renameTo(f)) {
            f.delete()
            tmp.renameTo(f)
        }
    }

    fun all(): List<Profile> = dir.listFiles { f -> f.extension == "json" }.orEmpty()
        .mapNotNull { Profile.parse(it.readText()) }.sortedBy { it.name.ifEmpty { it.id } }

    /** Phase 3-4a regions / Live mode from SharedPreferences become the default profile, once. */
    fun migrateOnce(prefs: Prefs) {
        if (prefs.profilesMigrated) return
        if (get(Profile.DEFAULT_ID) == null) save(ProfileLogic.migratePrefs(prefs.regions, prefs.liveScope))
        prefs.profilesMigrated = true
    }

    /** The user's own glossary terms for a game (filesDir/glossary/<id>.json, Windows format). */
    fun userGlossary(id: String) = File(File(context.filesDir, "glossary"), "$id.json")

    fun addTerms(id: String, terms: List<Pair<String, String?>>) {
        val f = userGlossary(id)
        val root = runCatching { JSONObject(f.readText()) }.getOrElse { JSONObject().put("entries", JSONArray()) }
        val entries = root.optJSONArray("entries") ?: JSONArray().also { root.put("entries", it) }
        for ((src, target) in terms) {
            entries.put(JSONObject().apply {
                put("source", src)
                put("type", if (target.isNullOrBlank()) "keep" else "map")
                if (!target.isNullOrBlank()) put("target", target)
                put("case_sensitive", true)
            })
        }
        f.parentFile?.mkdirs()
        f.writeText(root.toString(1))
    }

    /** corrections.jsonl (training data for Phase 6), same fields as Windows. */
    fun logCorrection(game: String, model: String, source: String, machine: String, corrected: String) {
        val row = JSONObject().apply {
            put("ts", System.currentTimeMillis() / 1000.0)
            put("game", game); put("model", model); put("source", source); put("machine", machine); put("corrected", corrected)
        }
        File(context.filesDir, "corrections.jsonl").appendText(row.toString() + "\n")
    }

    fun label(id: String): String = if (id == Profile.DEFAULT_ID) "Mặc định" else runCatching {
        val pm = context.packageManager
        @Suppress("DEPRECATION")  // the flags overload needs API 33; minSdk is 29
        val info = pm.getApplicationInfo(id, 0)
        pm.getApplicationLabel(info).toString()
    }.getOrDefault(id)
}

/** The app in front, from UsageStatsManager (needs Usage Access; without it: null, the user picks by hand). */
class GameDetector(private val context: Context) {
    fun hasAccess(): Boolean {
        val ops = context.getSystemService(AppOpsManager::class.java)
        return ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName) ==
            AppOpsManager.MODE_ALLOWED
    }

    fun current(): String? {
        if (!hasAccess()) return null
        val usm = context.getSystemService(UsageStatsManager::class.java) ?: return null
        val now = System.currentTimeMillis()
        val events = usm.queryEvents(now - 60_000, now)
        val e = UsageEvents.Event()
        var last: String? = null
        while (events.hasNextEvent()) {
            events.getNextEvent(e)
            if (e.eventType == UsageEvents.Event.ACTIVITY_RESUMED) last = e.packageName
        }
        return last
    }
}
