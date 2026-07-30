package code.soki.mobile.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class PairingPayloadTest {
    @Test
    fun parsesVersionedSokiPairingPayload() {
        val payload = PairingPayload.parse(
            """{"v":1,"type":"soki-code-pairing","pairing_id":"pair-1","code":"secret-code","api_base_url":"http://127.0.0.1:8000/"}""",
        )

        assertEquals("pair-1", payload.pairingId)
        assertEquals("secret-code", payload.code)
        assertEquals("http://127.0.0.1:8000", payload.apiBaseUrl)
    }

    @Test
    fun rejectsForeignQrCodes() {
        assertThrows(IllegalArgumentException::class.java) {
            PairingPayload.parse("""{"v":1,"type":"wifi","pairing_id":"x","code":"12345678","api_base_url":"http://x"}""")
        }
    }

    @Test
    fun parsesCompactTerminalPairingPayload() {
        val payload = PairingPayload.parse(
            "soki:1:Ej5FZ-ibEtOkVkJmFBdAAA:secret-code",
        )

        assertEquals("123e4567-e89b-12d3-a456-426614174000", payload.pairingId)
        assertEquals("secret-code", payload.code)
        assertEquals("http://127.0.0.1:8000", payload.apiBaseUrl)
    }
}
