package code.soki.mobile.data

import android.content.ContentResolver
import android.database.Cursor
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import okio.source
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class SokiApi {
    private val client = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(190, TimeUnit.SECONDS)
        .build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    suspend fun claim(payload: PairingPayload, deviceName: String): DeviceCredential =
        withContext(Dispatchers.IO) {
            val body = JSONObject()
                .put("pairing_id", payload.pairingId)
                .put("code", payload.code)
                .put("device_name", deviceName)
            val response = execute(
                Request.Builder()
                    .url("${payload.apiBaseUrl}/pairing/claim")
                    .post(body.toString().toRequestBody(jsonType))
                    .build(),
            )
            DeviceCredential(
                apiBaseUrl = response.getString("api_base_url").trimEnd('/'),
                deviceId = response.getString("device_id"),
                token = response.getString("device_token"),
                deviceName = deviceName,
            )
        }

    suspend fun status(credential: DeviceCredential): JSONObject = withContext(Dispatchers.IO) {
        execute(
            authorized(credential, "${credential.apiBaseUrl}/mobile/status")
                .get()
                .build(),
        )
    }

    suspend fun chat(
        credential: DeviceCredential,
        message: String,
        sessionId: String,
        history: List<ConversationMessage>,
        attachmentIds: List<String>,
    ): Pair<String, AgentTask?> = withContext(Dispatchers.IO) {
        val historyJson = JSONArray()
        history.takeLast(12).forEach {
            historyJson.put(
                JSONObject()
                    .put("role", if (it.role == ConversationMessage.Role.USER) "user" else "assistant")
                    .put("content", it.content),
            )
        }
        val body = JSONObject()
            .put("message", message)
            .put("session_id", sessionId)
            .put("history", historyJson)
            .put("attachment_ids", JSONArray(attachmentIds))
        val response = execute(
            authorized(credential, "${credential.apiBaseUrl}/mobile/chat")
                .post(body.toString().toRequestBody(jsonType))
                .build(),
        )
        response.getString("reply") to response.optJSONObject("proof")?.let(::parseTask)
    }

    suspend fun tasks(credential: DeviceCredential): List<AgentTask> =
        withContext(Dispatchers.IO) {
            val response = executeArray(
                authorized(credential, "${credential.apiBaseUrl}/mobile/tasks?limit=25")
                    .get()
                    .build(),
            )
            List(response.length()) { index -> parseTask(response.getJSONObject(index)) }
        }

    suspend fun attachments(credential: DeviceCredential): List<AgentAttachment> =
        withContext(Dispatchers.IO) {
            val response = executeArray(
                authorized(credential, "${credential.apiBaseUrl}/mobile/attachments")
                    .get()
                    .build(),
            )
            List(response.length()) { index -> parseAttachment(response.getJSONObject(index)) }
        }

    suspend fun uploadAttachment(
        credential: DeviceCredential,
        resolver: ContentResolver,
        uri: Uri,
    ): AgentAttachment = withContext(Dispatchers.IO) {
        val name = displayName(resolver, uri)
        val mediaType = resolver.getType(uri) ?: "application/octet-stream"
        val size = contentLength(resolver, uri)
        val fileBody = object : RequestBody() {
            override fun contentType() = mediaType.toMediaTypeOrNull()
            override fun contentLength() = size
            override fun writeTo(sink: BufferedSink) {
                resolver.openInputStream(uri)?.use { input ->
                    sink.writeAll(input.source())
                } ?: error("The selected file could not be opened.")
            }
        }
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", name, fileBody)
            .build()
        val response = execute(
            authorized(credential, "${credential.apiBaseUrl}/mobile/attachments")
                .removeHeader("Content-Type")
                .post(body)
                .build(),
        )
        parseAttachment(response)
    }

    private fun authorized(credential: DeviceCredential, url: String): Request.Builder {
        return Request.Builder()
            .url(url)
            .header("Authorization", "Bearer ${credential.token}")
            .header("Content-Type", "application/json")
    }

    private fun execute(request: Request): JSONObject {
        client.newCall(request).execute().use { response ->
            val text = response.body.string()
            if (!response.isSuccessful) throw ApiException(errorDetail(text, response.code), response.code)
            return try {
                JSONObject(text)
            } catch (error: JSONException) {
                throw ApiException(
                    "The laptop returned an invalid response. Restart Soki Code and pair again.",
                    response.code,
                )
            }
        }
    }

    private fun executeArray(request: Request): JSONArray {
        client.newCall(request).execute().use { response ->
            val text = response.body.string()
            if (!response.isSuccessful) throw ApiException(errorDetail(text, response.code), response.code)
            return try {
                JSONArray(text)
            } catch (error: JSONException) {
                throw ApiException(
                    "The laptop returned an invalid response. Restart Soki Code and pair again.",
                    response.code,
                )
            }
        }
    }

    private fun errorDetail(text: String, status: Int): String {
        return runCatching {
            val detail = JSONObject(text).opt("detail")
            when (detail) {
                is String -> detail
                is JSONObject -> detail.optString("message").ifBlank { detail.toString() }
                null, JSONObject.NULL -> ""
                else -> detail.toString()
            }
        }
            .getOrNull()
            ?.takeIf { it.isNotBlank() }
            ?: "The laptop returned HTTP $status."
    }

    private fun parseTask(payload: JSONObject): AgentTask {
        val checksJson = payload.optJSONArray("checks") ?: JSONArray()
        val checks = List(checksJson.length()) { index ->
            val check = checksJson.getJSONObject(index)
            ProofCheck(
                label = check.optString("label"),
                status = check.optString("status"),
                evidence = check.optString("evidence"),
            )
        }
        return AgentTask(
            id = payload.optString("task_id"),
            request = payload.optString("request"),
            response = payload.optString("response"),
            status = payload.optString("status"),
            runtime = payload.optString("runtime"),
            updatedAt = payload.optString("updated_at"),
            checks = checks,
        )
    }

    private fun parseAttachment(payload: JSONObject) = AgentAttachment(
        id = payload.getString("attachment_id"),
        name = payload.getString("name"),
        mediaType = payload.getString("media_type"),
        kind = payload.getString("kind"),
        sizeBytes = payload.getLong("size_bytes"),
        downloadUrl = payload.getString("download_url"),
    )

    private fun displayName(resolver: ContentResolver, uri: Uri): String {
        var cursor: Cursor? = null
        return try {
            cursor = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            if (cursor?.moveToFirst() == true) cursor.getString(0) else "attachment"
        } finally {
            cursor?.close()
        }
    }

    private fun contentLength(resolver: ContentResolver, uri: Uri): Long {
        var cursor: Cursor? = null
        return try {
            cursor = resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)
            if (cursor?.moveToFirst() == true) cursor.getLong(0) else -1L
        } finally {
            cursor?.close()
        }
    }
}

class ApiException(message: String, val statusCode: Int) : Exception(message)
