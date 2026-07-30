package code.soki.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.automirrored.rounded.FactCheck
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AttachFile
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FactCheck
import androidx.compose.material.icons.rounded.FolderOpen
import androidx.compose.material.icons.rounded.Menu
import androidx.compose.material.icons.rounded.PhoneAndroid
import androidx.compose.material.icons.rounded.QrCodeScanner
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import code.soki.mobile.data.AgentAttachment
import code.soki.mobile.data.AgentTask
import code.soki.mobile.data.ConversationMessage
import code.soki.mobile.ui.Amber
import code.soki.mobile.ui.Cobalt
import code.soki.mobile.ui.Danger
import code.soki.mobile.ui.Ground
import code.soki.mobile.ui.Hairline
import code.soki.mobile.ui.Ink
import code.soki.mobile.ui.Jade
import code.soki.mobile.ui.Muted
import code.soki.mobile.ui.PairingScanner
import code.soki.mobile.ui.Paper
import code.soki.mobile.ui.SokiTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            SokiTheme {
                val model: SokiViewModel = viewModel()
                SokiMobileApp(model)
            }
        }
    }
}

@Composable
private fun SokiMobileApp(model: SokiViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    var scanning by remember { mutableStateOf(false) }
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments(),
        model::addAttachments,
    )

    Surface(Modifier.fillMaxSize(), color = Paper) {
        when {
            state.checkingCredential -> LoadingScreen()
            state.credential == null && scanning -> PairingScanner(
                onScanned = {
                    scanning = false
                    model.pair(it)
                },
                onBack = { scanning = false },
            )
            state.credential == null -> PairingWelcome(
                state = state,
                onScan = { scanning = true },
                onManualPair = model::pair,
                onClearError = model::clearError,
            )
            else -> ConnectedWorkspace(
                state = state,
                onSend = model::send,
                onAttach = {
                    picker.launch(
                        arrayOf(
                            "image/*",
                            "video/*",
                            "audio/*",
                            "application/pdf",
                            "text/*",
                            "application/zip",
                        )
                    )
                },
                onRemoveAttachment = model::removePendingAttachment,
                onRefresh = model::refresh,
                onNewChat = model::newChat,
                onDisconnect = model::disconnect,
                onClearError = model::clearError,
            )
        }
    }
}

@Composable
private fun LoadingScreen() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            LogoMark(38)
            CircularProgressIndicator(
                modifier = Modifier.padding(top = 24.dp).size(20.dp),
                color = Cobalt,
                strokeWidth = 2.dp,
            )
        }
    }
}

@Composable
private fun PairingWelcome(
    state: SokiUiState,
    onScan: () -> Unit,
    onManualPair: (String) -> Unit,
    onClearError: () -> Unit,
) {
    var manualOpen by remember { mutableStateOf(false) }
    var payload by remember { mutableStateOf("") }
    Column(
        modifier = Modifier.fillMaxSize()
            .padding(WindowInsets.statusBars.asPaddingValues())
            .padding(horizontal = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.weight(1f))
        LogoMark(46)
        Text(
            "soki code",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(top = 18.dp),
        )
        Text(
            "Your agent, on your phone.",
            color = Muted,
            fontSize = 14.sp,
            modifier = Modifier.padding(top = 7.dp),
        )
        if (state.error.isNotBlank()) {
            ErrorBanner(state.error, onClearError, Modifier.padding(top = 20.dp))
        }
        if (manualOpen) {
            OutlinedTextField(
                value = payload,
                onValueChange = { payload = it },
                modifier = Modifier.fillMaxWidth().padding(top = 26.dp),
                placeholder = { Text("Paste pairing code") },
                minLines = 3,
                shape = RoundedCornerShape(14.dp),
            )
            Button(
                onClick = { onManualPair(payload) },
                enabled = payload.isNotBlank() && !state.pairing,
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(50.dp),
                shape = RoundedCornerShape(13.dp),
            ) {
                if (state.pairing) {
                    CircularProgressIndicator(Modifier.size(17.dp), Color.White, 2.dp)
                } else {
                    Text("Pair device")
                }
            }
        } else {
            Button(
                onClick = onScan,
                modifier = Modifier.fillMaxWidth().padding(top = 32.dp).height(52.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Ink),
            ) {
                Icon(Icons.Rounded.QrCodeScanner, null)
                Spacer(Modifier.width(9.dp))
                Text("Scan QR code")
            }
            Text(
                "Paste code instead",
                color = Muted,
                fontSize = 12.sp,
                modifier = Modifier.padding(15.dp).clickable { manualOpen = true },
            )
        }
        Spacer(Modifier.weight(1f))
        Row(
            modifier = Modifier.padding(
                bottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding() + 20.dp
            ),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.Security, null, tint = Jade, modifier = Modifier.size(15.dp))
            Text("One-time code · revocable access", color = Muted, fontSize = 10.sp, modifier = Modifier.padding(start = 7.dp))
        }
    }
}

@Composable
private fun ConnectedWorkspace(
    state: SokiUiState,
    onSend: (String) -> Unit,
    onAttach: () -> Unit,
    onRemoveAttachment: (String) -> Unit,
    onRefresh: () -> Unit,
    onNewChat: () -> Unit,
    onDisconnect: () -> Unit,
    onClearError: () -> Unit,
) {
    var page by remember { mutableIntStateOf(0) }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    ModalNavigationDrawer(
        drawerState = drawer,
        drawerContent = {
            ModalDrawerSheet(
                modifier = Modifier.fillMaxWidth(.84f).fillMaxHeight(),
                drawerContainerColor = Ground,
            ) {
                DrawerContent(
                    active = page,
                    state = state,
                    onSelect = {
                        page = it
                        scope.launch { drawer.close() }
                    },
                    onNewChat = {
                        onNewChat()
                        page = 0
                        scope.launch { drawer.close() }
                    },
                    onDisconnect = onDisconnect,
                )
            }
        },
    ) {
        Scaffold(
            containerColor = Paper,
            contentWindowInsets = WindowInsets(0),
            topBar = {
                AppHeader(
                    connected = state.hermesVerified,
                    onMenu = { scope.launch { drawer.open() } },
                    onNewChat = {
                        onNewChat()
                        page = 0
                    },
                )
            },
        ) { padding ->
            Box(Modifier.fillMaxSize().padding(padding)) {
                when (page) {
                    0 -> ChatScreen(
                        state,
                        onSend,
                        onAttach,
                        onRemoveAttachment,
                    )
                    1 -> ProofScreen(state.tasks, onRefresh)
                    2 -> FilesScreen(state.files, onAttach)
                    else -> DeviceScreen(state, onRefresh, onDisconnect)
                }
                if (state.error.isNotBlank()) {
                    ErrorBanner(
                        state.error,
                        onClearError,
                        Modifier.align(Alignment.BottomCenter).padding(12.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun AppHeader(connected: Boolean, onMenu: () -> Unit, onNewChat: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth()
            .background(Paper)
            .padding(WindowInsets.statusBars.asPaddingValues())
            .height(54.dp)
            .padding(horizontal = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onMenu) { Icon(Icons.Rounded.Menu, "Menu") }
        Spacer(Modifier.weight(1f))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(7.dp).background(if (connected) Jade else Amber, CircleShape))
            Text("soki code", fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.padding(start = 8.dp))
        }
        Spacer(Modifier.weight(1f))
        IconButton(onClick = onNewChat) { Icon(Icons.Rounded.Add, "New chat") }
    }
}

@Composable
private fun DrawerContent(
    active: Int,
    state: SokiUiState,
    onSelect: (Int) -> Unit,
    onNewChat: () -> Unit,
    onDisconnect: () -> Unit,
) {
    Column(
        Modifier.fillMaxSize()
            .padding(WindowInsets.statusBars.asPaddingValues())
            .padding(12.dp),
    ) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            LogoMark(28)
            Text("soki code", fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 9.dp))
        }
        Button(
            onClick = onNewChat,
            modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Paper, contentColor = Ink),
            shape = RoundedCornerShape(11.dp),
        ) {
            Icon(Icons.Rounded.Add, null, Modifier.size(18.dp))
            Text("New chat", modifier = Modifier.padding(start = 8.dp))
        }
        Spacer(Modifier.height(12.dp))
        DrawerItem(Icons.Rounded.Description, "Chat", active == 0) { onSelect(0) }
        DrawerItem(Icons.AutoMirrored.Rounded.FactCheck, "Proof", active == 1) { onSelect(1) }
        DrawerItem(Icons.Rounded.FolderOpen, "Files", active == 2) { onSelect(2) }
        DrawerItem(Icons.Rounded.PhoneAndroid, "Device", active == 3) { onSelect(3) }
        Spacer(Modifier.weight(1f))
        HorizontalDivider(color = Hairline)
        Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).background(Ink, CircleShape), contentAlignment = Alignment.Center) {
                Text("SC", color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            }
            Column(Modifier.weight(1f).padding(start = 10.dp)) {
                Text(state.credential?.deviceName.orEmpty(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text("Paired", fontSize = 10.sp, color = Muted)
            }
            IconButton(onClick = onDisconnect) {
                Icon(Icons.AutoMirrored.Rounded.Logout, "Disconnect", tint = Danger)
            }
        }
    }
}

@Composable
private fun DrawerItem(icon: ImageVector, label: String, active: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth()
            .background(if (active) Paper else Color.Transparent, RoundedCornerShape(10.dp))
            .clickable(onClick = onClick)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, null, tint = if (active) Ink else Muted, modifier = Modifier.size(19.dp))
        Text(label, fontSize = 13.sp, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal, modifier = Modifier.padding(start = 11.dp))
    }
}

@Composable
private fun ChatScreen(
    state: SokiUiState,
    onSend: (String) -> Unit,
    onAttach: () -> Unit,
    onRemoveAttachment: (String) -> Unit,
) {
    var draft by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    val focusManager = LocalFocusManager.current
    LaunchedEffect(state.messages.size, state.sending) {
        if (state.messages.isNotEmpty()) listState.animateScrollToItem(state.messages.lastIndex + 1)
    }
    Column(Modifier.fillMaxSize().imePadding()) {
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp, 22.dp, 16.dp, 24.dp),
            verticalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            items(state.messages, key = { it.id }) { MessageBubble(it) }
            if (state.sending) item("working") { WorkingIndicator() }
        }
        Composer(
            draft = draft,
            attachments = state.pendingAttachments,
            sending = state.sending,
            uploading = state.uploading,
            onDraft = { draft = it },
            onAttach = onAttach,
            onRemoveAttachment = onRemoveAttachment,
            onSend = {
                if (draft.isNotBlank() || state.pendingAttachments.isNotEmpty()) {
                    onSend(draft)
                    draft = ""
                    focusManager.clearFocus()
                }
            },
        )
    }
}

@Composable
private fun MessageBubble(message: ConversationMessage) {
    val user = message.role == ConversationMessage.Role.USER
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (user) Arrangement.End else Arrangement.Start) {
        Column(
            modifier = Modifier.fillMaxWidth(if (user) .86f else 1f)
                .then(
                    if (user) Modifier.background(Ground, RoundedCornerShape(18.dp, 18.dp, 5.dp, 18.dp))
                        .padding(13.dp, 10.dp)
                    else Modifier
                ),
        ) {
            if (message.attachments.isNotEmpty()) {
                message.attachments.forEach { AttachmentRow(it, compact = true) }
                Spacer(Modifier.height(8.dp))
            }
            Text(message.content, fontSize = 14.sp, lineHeight = 21.sp, color = Ink)
            message.task?.let {
                Row(
                    modifier = Modifier.padding(top = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.AutoMirrored.Rounded.FactCheck, null, tint = Jade, modifier = Modifier.size(14.dp))
                    Text(
                        if (it.status == "VERIFIED") "Verified" else "View progress",
                        color = Jade,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(start = 5.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun Composer(
    draft: String,
    attachments: List<AgentAttachment>,
    sending: Boolean,
    uploading: Boolean,
    onDraft: (String) -> Unit,
    onAttach: () -> Unit,
    onRemoveAttachment: (String) -> Unit,
    onSend: () -> Unit,
) {
    Column(
        Modifier.fillMaxWidth()
            .background(Paper)
            .padding(horizontal = 10.dp, vertical = 8.dp)
            .padding(bottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()),
    ) {
        Column(
            Modifier.fillMaxWidth()
                .border(1.dp, Hairline, RoundedCornerShape(19.dp))
                .background(Paper, RoundedCornerShape(19.dp))
                .padding(7.dp),
        ) {
            attachments.forEach { attachment ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { AttachmentRow(attachment, compact = true) }
                    IconButton(onClick = { onRemoveAttachment(attachment.id) }, modifier = Modifier.size(30.dp)) {
                        Icon(Icons.Rounded.Close, "Remove", modifier = Modifier.size(15.dp))
                    }
                }
            }
            OutlinedTextField(
                value = draft,
                onValueChange = onDraft,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text(if (uploading) "Uploading…" else "Message soki code", fontSize = 14.sp) },
                maxLines = 5,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
                colors = androidx.compose.material3.OutlinedTextFieldDefaults.colors(
                    unfocusedBorderColor = Color.Transparent,
                    focusedBorderColor = Color.Transparent,
                ),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onAttach, enabled = !uploading && attachments.size < 8) {
                    Icon(Icons.Rounded.AttachFile, "Add photo, video, or file")
                }
                Text("Photos, video & files", color = Muted, fontSize = 10.sp)
                Spacer(Modifier.weight(1f))
                IconButton(
                    onClick = onSend,
                    enabled = !sending && !uploading && (draft.isNotBlank() || attachments.isNotEmpty()),
                    modifier = Modifier.size(38.dp).background(
                        if (draft.isNotBlank() || attachments.isNotEmpty()) Ink else Ground,
                        CircleShape,
                    ),
                ) {
                    Icon(Icons.AutoMirrored.Rounded.Send, "Send", tint = if (draft.isNotBlank() || attachments.isNotEmpty()) Color.White else Muted, modifier = Modifier.size(18.dp))
                }
            }
        }
        Text(
            "Review important work and trading decisions.",
            color = Muted,
            fontSize = 9.sp,
            modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 6.dp),
        )
    }
}

@Composable
private fun WorkingIndicator() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.size(18.dp), Cobalt, 2.dp)
        Text("Working…", color = Muted, fontSize = 11.sp, modifier = Modifier.padding(start = 9.dp))
    }
}

@Composable
private fun ProofScreen(tasks: List<AgentTask>, onRefresh: () -> Unit) {
    LibraryHeader("Proof", "Completed and interrupted work.", onRefresh)
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 82.dp, 18.dp, 28.dp),
    ) {
        if (tasks.isEmpty()) {
            item { EmptyState(Icons.AutoMirrored.Rounded.FactCheck, "No proof records yet") }
        }
        items(tasks, key = { it.id }) { task ->
            Row(Modifier.fillMaxWidth().padding(vertical = 15.dp), verticalAlignment = Alignment.Top) {
                Box(
                    Modifier.size(29.dp).background(if (task.status == "VERIFIED") Color(0xFFE3F2EE) else Ground, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    if (task.status == "VERIFIED") Icon(Icons.Rounded.Check, null, tint = Jade, modifier = Modifier.size(15.dp))
                }
                Column(Modifier.weight(1f).padding(start = 12.dp)) {
                    Text(task.request, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(task.response.ifBlank { "Work is still in progress." }, color = Muted, fontSize = 11.sp, lineHeight = 16.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 4.dp))
                    Text(task.status.lowercase(), color = if (task.status == "VERIFIED") Jade else Muted, fontSize = 9.sp, modifier = Modifier.padding(top = 5.dp))
                }
            }
            HorizontalDivider(color = Hairline)
        }
    }
}

@Composable
private fun FilesScreen(files: List<AgentAttachment>, onAttach: () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        Column {
            Row(
                Modifier.fillMaxWidth().height(70.dp).padding(horizontal = 18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Files", fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                    Text("Items shared with Soki.", color = Muted, fontSize = 11.sp)
                }
                Button(onClick = onAttach, colors = ButtonDefaults.buttonColors(containerColor = Ink), shape = RoundedCornerShape(11.dp)) {
                    Icon(Icons.Rounded.Add, null, Modifier.size(17.dp))
                    Text("Add file", modifier = Modifier.padding(start = 6.dp), fontSize = 11.sp)
                }
            }
            HorizontalDivider(color = Hairline)
            if (files.isEmpty()) {
                EmptyState(Icons.Rounded.FolderOpen, "No files yet")
            } else {
                LazyColumn(contentPadding = PaddingValues(18.dp, 10.dp, 18.dp, 28.dp)) {
                    items(files, key = { it.id }) { AttachmentRow(it) }
                }
            }
        }
    }
}

@Composable
private fun AttachmentRow(file: AgentAttachment, compact: Boolean = false) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = if (compact) 3.dp else 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(if (compact) 31.dp else 39.dp).background(Ground, RoundedCornerShape(9.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.Description, null, tint = Muted, modifier = Modifier.size(if (compact) 16.dp else 19.dp))
        }
        Column(Modifier.weight(1f).padding(start = 9.dp)) {
            Text(file.name, fontSize = if (compact) 10.sp else 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(formatBytes(file.sizeBytes), color = Muted, fontSize = 9.sp)
        }
    }
}

@Composable
private fun DeviceScreen(state: SokiUiState, onRefresh: () -> Unit, onDisconnect: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(22.dp)) {
        Text("Device", fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
        Text("Connected to your local Soki workspace.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
        Column(
            Modifier.fillMaxWidth().padding(top = 25.dp).border(1.dp, Hairline, RoundedCornerShape(14.dp)).padding(16.dp),
        ) {
            Text(state.credential?.deviceName.orEmpty(), fontWeight = FontWeight.SemiBold)
            Text(state.credential?.apiBaseUrl.orEmpty(), color = Muted, fontSize = 10.sp, modifier = Modifier.padding(top = 4.dp))
            HorizontalDivider(color = Hairline, modifier = Modifier.padding(vertical = 14.dp))
            Text(if (state.hermesVerified) "Agent connected" else "Agent fallback active", color = if (state.hermesVerified) Jade else Amber, fontSize = 11.sp)
            Text("Research and paper trading only", color = Muted, fontSize = 10.sp, modifier = Modifier.padding(top = 5.dp))
        }
        Button(
            onClick = onRefresh,
            modifier = Modifier.fillMaxWidth().padding(top = 13.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Ink),
            shape = RoundedCornerShape(12.dp),
        ) {
            Icon(Icons.Rounded.Refresh, null, Modifier.size(17.dp))
            Text("Check connection", modifier = Modifier.padding(start = 7.dp))
        }
        Spacer(Modifier.weight(1f))
        Row(
            Modifier.fillMaxWidth().clickable(onClick = onDisconnect).padding(vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.AutoMirrored.Rounded.Logout, null, tint = Danger)
            Text("Forget this laptop", color = Danger, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 9.dp))
        }
    }
}

@Composable
private fun LibraryHeader(title: String, subtitle: String, onRefresh: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(70.dp).padding(horizontal = 18.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
            Text(subtitle, color = Muted, fontSize = 11.sp)
        }
        IconButton(onClick = onRefresh) { Icon(Icons.Rounded.Refresh, "Refresh") }
    }
}

@Composable
private fun EmptyState(icon: ImageVector, label: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 90.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(icon, null, tint = Muted, modifier = Modifier.size(29.dp))
        Text(label, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp))
    }
}

@Composable
private fun ErrorBanner(message: String, onClose: () -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().border(1.dp, Color(0xFFE2B7B7), RoundedCornerShape(11.dp))
            .background(Color(0xFFFFF5F5), RoundedCornerShape(11.dp)).padding(11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(message, color = Danger, fontSize = 10.sp, lineHeight = 15.sp, modifier = Modifier.weight(1f))
        IconButton(onClick = onClose, modifier = Modifier.size(26.dp)) {
            Icon(Icons.Rounded.Close, "Dismiss", tint = Danger, modifier = Modifier.size(15.dp))
        }
    }
}

@Composable
private fun LogoMark(size: Int = 29) {
    Box(
        Modifier.size(size.dp).background(Ink, RoundedCornerShape((size / 4).dp, (size / 2).dp, (size / 4).dp, (size / 4).dp)),
        contentAlignment = Alignment.Center,
    ) {
        Text("s", color = Color.White, fontWeight = FontWeight.Bold, fontSize = (size * .56).sp)
    }
}

private fun formatBytes(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "${"%.1f".format(bytes / 1024.0)} KB"
    else -> "${"%.1f".format(bytes / (1024.0 * 1024.0))} MB"
}
