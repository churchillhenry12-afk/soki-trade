package code.soki.mobile

import android.app.Application
import android.os.Build
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import code.soki.mobile.data.AgentTask
import code.soki.mobile.data.AgentAttachment
import code.soki.mobile.data.ApiException
import code.soki.mobile.data.ConversationMessage
import code.soki.mobile.data.DeviceCredential
import code.soki.mobile.data.PairingPayload
import code.soki.mobile.data.SecureDeviceStore
import code.soki.mobile.data.SokiApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

data class SokiUiState(
    val credential: DeviceCredential? = null,
    val checkingCredential: Boolean = true,
    val pairing: Boolean = false,
    val sending: Boolean = false,
    val uploading: Boolean = false,
    val hermesVerified: Boolean = false,
    val messages: List<ConversationMessage> = listOf(
        ConversationMessage(
            id = "welcome",
            role = ConversationMessage.Role.AGENT,
            content = "Hi — what can I help you get done?",
        ),
    ),
    val tasks: List<AgentTask> = emptyList(),
    val files: List<AgentAttachment> = emptyList(),
    val pendingAttachments: List<AgentAttachment> = emptyList(),
    val error: String = "",
)

class SokiViewModel(application: Application) : AndroidViewModel(application) {
    private val api = SokiApi()
    private val store = SecureDeviceStore(application)
    private val mutableState = MutableStateFlow(SokiUiState())
    val state: StateFlow<SokiUiState> = mutableState.asStateFlow()

    init {
        validateStoredCredential()
    }

    fun pair(rawPayload: String) {
        mutableState.update { it.copy(pairing = true, error = "") }
        viewModelScope.launch {
            runCatching {
                val payload = PairingPayload.parse(rawPayload)
                api.claim(payload, "${Build.MANUFACTURER} ${Build.MODEL}".trim())
            }.onSuccess { credential ->
                store.save(credential)
                mutableState.update {
                    it.copy(
                        credential = credential,
                        pairing = false,
                        checkingCredential = false,
                    )
                }
                refresh()
            }.onFailure { error ->
                mutableState.update {
                    it.copy(pairing = false, error = error.message ?: "Pairing failed.")
                }
            }
        }
    }

    fun send(message: String) {
        val credential = state.value.credential ?: return
        val text = message.trim()
        val attachments = state.value.pendingAttachments
        if ((text.isEmpty() && attachments.isEmpty()) || state.value.sending || state.value.uploading) return
        val resolvedText = text.ifEmpty { "Please review the attached files." }
        val userMessage = ConversationMessage(
            id = UUID.randomUUID().toString(),
            role = ConversationMessage.Role.USER,
            content = resolvedText,
            attachments = attachments,
        )
        val history = state.value.messages
        mutableState.update {
            it.copy(
                messages = it.messages + userMessage,
                pendingAttachments = emptyList(),
                sending = true,
                error = "",
            )
        }
        viewModelScope.launch {
            runCatching {
                api.chat(
                    credential = credential,
                    message = resolvedText,
                    sessionId = "mobile-${credential.deviceId}-main",
                    history = history,
                    attachmentIds = attachments.map { it.id },
                )
            }.onSuccess { (reply, task) ->
                mutableState.update {
                    it.copy(
                        sending = false,
                        messages = it.messages + ConversationMessage(
                            id = task?.id ?: UUID.randomUUID().toString(),
                            role = ConversationMessage.Role.AGENT,
                            content = reply,
                            task = task,
                        ),
                    )
                }
                refreshTasks()
            }.onFailure(::handleApiFailure)
        }
    }

    fun refresh() {
        val credential = state.value.credential ?: return
        viewModelScope.launch {
            runCatching {
                val status = api.status(credential)
                val tasks = api.tasks(credential)
                val files = api.attachments(credential)
                Triple(status, tasks, files)
            }.onSuccess { (status, tasks, files) ->
                mutableState.update {
                    it.copy(
                        checkingCredential = false,
                        hermesVerified = status.optJSONObject("hermes")?.optBoolean("verified") == true,
                        tasks = tasks,
                        files = files,
                        error = "",
                    )
                }
            }.onFailure(::handleApiFailure)
        }
    }

    fun disconnect() {
        store.clear()
        mutableState.value = SokiUiState(checkingCredential = false)
    }

    fun addAttachments(uris: List<Uri>) {
        val credential = state.value.credential ?: return
        if (uris.isEmpty() || state.value.uploading) return
        val remaining = (8 - state.value.pendingAttachments.size).coerceAtLeast(0)
        val selected = uris.take(remaining)
        if (selected.isEmpty()) return
        mutableState.update { it.copy(uploading = true, error = "") }
        viewModelScope.launch {
            runCatching {
                selected.map { uri ->
                    api.uploadAttachment(credential, getApplication<Application>().contentResolver, uri)
                }
            }.onSuccess { uploaded ->
                mutableState.update {
                    it.copy(
                        uploading = false,
                        pendingAttachments = it.pendingAttachments + uploaded,
                        files = uploaded + it.files,
                    )
                }
            }.onFailure { error ->
                mutableState.update {
                    it.copy(uploading = false, error = error.message ?: "The upload failed.")
                }
            }
        }
    }

    fun removePendingAttachment(id: String) {
        mutableState.update {
            it.copy(pendingAttachments = it.pendingAttachments.filterNot { file -> file.id == id })
        }
    }

    fun newChat() {
        mutableState.update {
            it.copy(
                messages = listOf(
                    ConversationMessage(
                        id = "welcome-${UUID.randomUUID()}",
                        role = ConversationMessage.Role.AGENT,
                        content = "Hi — what can I help you get done?",
                    )
                ),
                pendingAttachments = emptyList(),
                error = "",
            )
        }
    }

    fun clearError() {
        mutableState.update { it.copy(error = "") }
    }

    private fun validateStoredCredential() {
        val credential = store.load()
        if (credential == null) {
            mutableState.update { it.copy(checkingCredential = false) }
            return
        }
        mutableState.update { it.copy(credential = credential) }
        refresh()
    }

    private fun refreshTasks() {
        val credential = state.value.credential ?: return
        viewModelScope.launch {
            runCatching { api.tasks(credential) }
                .onSuccess { tasks -> mutableState.update { it.copy(tasks = tasks) } }
        }
    }

    private fun handleApiFailure(error: Throwable) {
        if (error is ApiException && error.statusCode == 401) {
            store.clear()
            mutableState.update {
                it.copy(
                    credential = null,
                    checkingCredential = false,
                    sending = false,
                    error = "This phone is no longer paired. Scan a new code from the laptop.",
                )
            }
            return
        }
        mutableState.update {
            it.copy(
                checkingCredential = false,
                sending = false,
                uploading = false,
                error = error.message ?: "The laptop could not be reached.",
            )
        }
    }
}
