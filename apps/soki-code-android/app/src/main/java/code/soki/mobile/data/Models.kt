package code.soki.mobile.data

data class DeviceCredential(
    val apiBaseUrl: String,
    val deviceId: String,
    val token: String,
    val deviceName: String,
)

data class ProofCheck(
    val label: String,
    val status: String,
    val evidence: String,
)

data class AgentTask(
    val id: String,
    val request: String,
    val response: String,
    val status: String,
    val runtime: String,
    val updatedAt: String,
    val checks: List<ProofCheck>,
)

data class ConversationMessage(
    val id: String,
    val role: Role,
    val content: String,
    val task: AgentTask? = null,
    val attachments: List<AgentAttachment> = emptyList(),
) {
    enum class Role { USER, AGENT }
}

data class AgentAttachment(
    val id: String,
    val name: String,
    val mediaType: String,
    val kind: String,
    val sizeBytes: Long,
    val downloadUrl: String,
)
