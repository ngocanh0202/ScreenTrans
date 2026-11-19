package dev.screentrans.engine

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import dev.screentrans.core.llm.KeyProvider
import dev.screentrans.core.llm.cleanKey
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * API keys of the remote translation engines, encrypted with an AES/GCM key kept in the Android Keystore
 * (never leaves the secure hardware). Ciphertext in private prefs "llm_keys". Unreadable (key invalidated,
 * Keystore unavailable) -> "" (the user enters it again); never throws, never logs.
 */
class KeyVault(context: Context) : KeyProvider {
    private val prefs = context.getSharedPreferences("llm_keys", Context.MODE_PRIVATE)

    private fun secret(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build())
        return gen.generateKey()
    }

    override fun key(engine: String): String = try {
        val stored = prefs.getString(engine, null) ?: return ""
        val raw = Base64.decode(stored, Base64.NO_WRAP)
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.DECRYPT_MODE, secret(), GCMParameterSpec(128, raw, 0, IV))
        String(cipher.doFinal(raw, IV, raw.size - IV), Charsets.UTF_8)
    } catch (e: Exception) {
        ""
    }

    fun has(engine: String) = key(engine).isNotEmpty()

    /** Empty (after cleaning) removes the key. */
    fun set(engine: String, key: String) {
        val k = cleanKey(key)
        if (k.isEmpty()) {
            prefs.edit().remove(engine).apply()
            return
        }
        try {
            val cipher = Cipher.getInstance(TRANSFORM)
            cipher.init(Cipher.ENCRYPT_MODE, secret())
            val out = cipher.iv + cipher.doFinal(k.toByteArray(Charsets.UTF_8))
            prefs.edit().putString(engine, Base64.encodeToString(out, Base64.NO_WRAP)).apply()
        } catch (e: Exception) {
            // Keystore unavailable: the key is not saved (the settings say so: no "đã lưu")
        }
    }

    private companion object {
        const val ALIAS = "screentrans_llm_keys"
        const val TRANSFORM = "AES/GCM/NoPadding"
        const val IV = 12
    }
}
