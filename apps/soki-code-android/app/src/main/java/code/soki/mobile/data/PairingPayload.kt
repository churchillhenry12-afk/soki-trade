package code.soki.mobile.data

import org.json.JSONObject
import java.nio.ByteBuffer
import java.util.Base64
import java.util.UUID

data class PairingPayload(
    val pairingId: String,
    val code: String,
    val apiBaseUrl: String,
) {
    companion object {
        fun parse(raw: String): PairingPayload {
            if (raw.startsWith("soki:")) {
                return parseCompact(raw)
            }
            val payload = JSONObject(raw)
            require(payload.optInt("v") == 1) { "Unsupported pairing code version." }
            require(payload.optString("type") == "soki-code-pairing") {
                "This QR code was not created by soki code."
            }
            val pairingId = payload.getString("pairing_id").trim()
            val code = payload.getString("code").trim()
            val apiBaseUrl = payload.getString("api_base_url").trim().trimEnd('/')
            require(pairingId.isNotEmpty() && code.length >= 8) { "The pairing code is incomplete." }
            require(apiBaseUrl.startsWith("http://") || apiBaseUrl.startsWith("https://")) {
                "The laptop address is invalid."
            }
            return PairingPayload(pairingId, code, apiBaseUrl)
        }

        private fun parseCompact(raw: String): PairingPayload {
            val parts = raw.split(':', limit = 5)
            require(parts.size >= 4 && parts[0] == "soki" && parts[1] == "1") {
                "Unsupported pairing code version."
            }
            val pairingBytes = Base64.getUrlDecoder().decode(parts[2])
            require(pairingBytes.size == 16) { "The pairing code is incomplete." }
            val buffer = ByteBuffer.wrap(pairingBytes)
            val pairingId = UUID(buffer.long, buffer.long).toString()
            val code = parts[3].trim()
            val apiBaseUrl = if (parts.size == 5) {
                String(Base64.getUrlDecoder().decode(parts[4]), Charsets.UTF_8)
            } else {
                "http://127.0.0.1:8000"
            }.trimEnd('/')
            require(code.length >= 8) { "The pairing code is incomplete." }
            require(apiBaseUrl.startsWith("http://") || apiBaseUrl.startsWith("https://")) {
                "The laptop address is invalid."
            }
            return PairingPayload(pairingId, code, apiBaseUrl)
        }
    }
}
