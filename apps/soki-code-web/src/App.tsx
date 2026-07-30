import {
  ArrowUp,
  Check,
  ChevronRight,
  File,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  Menu,
  MessageSquare,
  MonitorCog,
  MoreHorizontal,
  Paperclip,
  Plus,
  RotateCw,
  Settings,
  ShieldCheck,
  Smartphone,
  Trash2,
  Video,
  X,
} from "lucide-react";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { QRCodeSVG } from "qrcode.react";
import { api } from "./api";
import type {
  AgentTask,
  Attachment,
  ChatMessage,
  PairedDevice,
  PairingSession,
  SetupStatus,
} from "./types";

type View = "chat" | "proof" | "files";
type Dialog = "settings" | "pair" | "devices" | null;

const suggestions = [
  "Backtest EURUSD on M15",
  "Review these files and make a plan",
  "Show what is connected",
];

function makeId() {
  return crypto.randomUUID();
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function attachmentIcon(kind: Attachment["kind"]) {
  if (kind === "IMAGE") return <ImageIcon size={17} />;
  if (kind === "VIDEO") return <Video size={17} />;
  return <FileText size={17} />;
}

export function App() {
  const [view, setView] = useState<View>("chat");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [library, setLibrary] = useState<Attachment[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<Attachment[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useMemo(() => `desktop-${crypto.randomUUID()}`, []);

  async function refresh() {
    try {
      const [nextSetup, nextTasks, nextLibrary] = await Promise.all([
        api.setup(),
        api.tasks(),
        api.attachments(),
      ]);
      setSetup(nextSetup);
      setTasks(nextTasks);
      setLibrary(nextLibrary);
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Soki is offline.");
    }
  }

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, sending]);

  async function uploadFiles(files: FileList | File[]) {
    const selected = Array.from(files).slice(0, Math.max(0, 8 - pending.length));
    if (!selected.length) return;
    setUploading(true);
    setNotice("");
    try {
      const uploaded = await Promise.all(selected.map((file) => api.uploadAttachment(file)));
      setPending((current) => [...current, ...uploaded].slice(0, 8));
      setLibrary((current) => [...uploaded, ...current]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The upload failed.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function sendMessage(value = draft) {
    const text = value.trim();
    if ((!text && !pending.length) || sending || uploading) return;
    const content = text || "Please review the attached files.";
    const attached = pending;
    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      content,
      attachments: attached,
    };
    const history = messages.map(({ role, content: itemContent }) => ({
      role,
      content: itemContent,
    }));
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setPending([]);
    setSending(true);
    setNotice("");
    try {
      const response = await api.chat(
        content,
        sessionId,
        history,
        attached.map((item) => item.attachment_id),
      );
      setMessages((current) => [
        ...current,
        {
          id: response.task_id ?? makeId(),
          role: "assistant",
          content: response.reply,
          task: response.proof,
          runtime: response.runtime,
        },
      ]);
      await refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "The request stopped.";
      setNotice(message);
      setMessages((current) => [
        ...current,
        {
          id: makeId(),
          role: "assistant",
          content: `I couldn’t finish that request. ${message}`,
        },
      ]);
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }

  function newChat() {
    setMessages([]);
    setDraft("");
    setPending([]);
    setView("chat");
    setSidebarOpen(false);
  }

  return (
    <div
      className="workspace"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        void uploadFiles(event.dataTransfer.files);
      }}
    >
      <aside className={`sidebar ${sidebarOpen ? "is-open" : ""}`}>
        <div className="brand-row">
          <button className="brand" onClick={newChat}>
            <span>s</span>
            soki code
          </button>
          <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close menu">
            <X size={19} />
          </button>
        </div>

        <button className="new-chat" onClick={newChat}>
          <Plus size={17} />
          New chat
        </button>

        <nav className="primary-nav">
          <NavButton
            icon={<MessageSquare size={18} />}
            label="Chat"
            active={view === "chat"}
            onClick={() => setView("chat")}
          />
          <NavButton
            icon={<ShieldCheck size={18} />}
            label="Proof"
            count={tasks.length}
            active={view === "proof"}
            onClick={() => setView("proof")}
          />
          <NavButton
            icon={<FolderOpen size={18} />}
            label="Files"
            count={library.length}
            active={view === "files"}
            onClick={() => setView("files")}
          />
        </nav>

        <div className="sidebar-bottom">
          <button className="sidebar-action" onClick={() => setDialog("pair")}>
            <Smartphone size={18} />
            Pair phone
          </button>
          <button className="sidebar-action" onClick={() => setDialog("settings")}>
            <Settings size={18} />
            Settings
          </button>
          <button className="account-row" onClick={() => setDialog("settings")}>
            <span className="account-mark">SC</span>
            <span>
              <strong>Local workspace</strong>
              <small>{setup?.agent.ready ? "Ready" : "Needs attention"}</small>
            </span>
            <MoreHorizontal size={17} />
          </button>
        </div>
      </aside>
      {sidebarOpen && <button className="scrim" onClick={() => setSidebarOpen(false)} aria-label="Close menu" />}

      <main className="main-panel">
        <header className="mobile-header">
          <button className="header-icon" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <Menu size={21} />
          </button>
          <button className="mobile-title" onClick={() => setView("chat")}>soki code</button>
          <button className="header-icon" onClick={newChat} aria-label="New chat">
            <Plus size={21} />
          </button>
        </header>

        {view === "chat" && (
          <section className={`chat-view ${messages.length ? "has-messages" : ""}`}>
            <div className="conversation">
              {!messages.length && (
                <div className="empty-state">
                  <div className="empty-mark">s</div>
                  <h1>What can I help you get done?</h1>
                  <div className="suggestions">
                    {suggestions.map((suggestion) => (
                      <button key={suggestion} onClick={() => void sendMessage(suggestion)}>
                        {suggestion}
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message) => (
                <article className={`chat-message ${message.role}`} key={message.id}>
                  <div className="message-content">
                    {message.attachments?.length ? (
                      <div className="message-attachments">
                        {message.attachments.map((item) => (
                          <AttachmentChip item={item} key={item.attachment_id} />
                        ))}
                      </div>
                    ) : null}
                    <div className="markdown">
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                    {message.task && (
                      <button className="proof-link" onClick={() => setView("proof")}>
                        <ShieldCheck size={14} />
                        {message.task.status === "VERIFIED" ? "Verified" : "View progress"}
                      </button>
                    )}
                  </div>
                </article>
              ))}

              {sending && (
                <article className="chat-message assistant">
                  <div className="message-content typing" aria-label="Soki is working">
                    <i />
                    <i />
                    <i />
                  </div>
                </article>
              )}
              <div ref={threadEndRef} />
            </div>

            <Composer
              draft={draft}
              pending={pending}
              sending={sending}
              uploading={uploading}
              textareaRef={textareaRef}
              fileRef={fileRef}
              onDraft={setDraft}
              onFiles={uploadFiles}
              onRemove={(id) =>
                setPending((current) => current.filter((item) => item.attachment_id !== id))
              }
              onSend={sendMessage}
            />
          </section>
        )}

        {view === "proof" && (
          <LibraryView
            title="Proof"
            description="A compact record of completed and interrupted work."
            action={<button className="round-action" onClick={() => void refresh()}><RotateCw size={17} /></button>}
          >
            {tasks.length ? (
              <div className="task-list">
                {tasks.map((task) => (
                  <article className="task-row" key={task.task_id}>
                    <span className={`task-status status-${task.status.toLowerCase()}`}>
                      {task.status === "VERIFIED" ? <Check size={15} /> : <MoreHorizontal size={15} />}
                    </span>
                    <div>
                      <strong>{task.request}</strong>
                      <p>{task.response || task.error || "Work is still in progress."}</p>
                      <small>{task.status.toLowerCase()} · {new Date(task.updated_at).toLocaleString()}</small>
                    </div>
                  </article>
                ))}
              </div>
            ) : <EmptyLibrary icon={<ShieldCheck />} label="No proof records yet" />}
          </LibraryView>
        )}

        {view === "files" && (
          <LibraryView
            title="Files"
            description="Items you have shared with Soki."
            action={
              <button className="add-file-button" onClick={() => fileRef.current?.click()}>
                <Plus size={16} /> Add file
              </button>
            }
          >
            {library.length ? (
              <div className="file-grid">
                {library.map((item) => (
                  <a
                    className="file-card"
                    href={`${api.baseUrl}${item.download_url}`}
                    target="_blank"
                    rel="noreferrer"
                    key={item.attachment_id}
                  >
                    <span>{attachmentIcon(item.kind)}</span>
                    <strong>{item.name}</strong>
                    <small>{formatSize(item.size_bytes)}</small>
                  </a>
                ))}
              </div>
            ) : <EmptyLibrary icon={<File />} label="No files yet" />}
          </LibraryView>
        )}

        {notice && (
          <div className="notice" role="alert">
            <span>{notice}</span>
            <button onClick={() => setNotice("")}><X size={16} /></button>
          </div>
        )}
      </main>

      {dialog === "settings" && (
        <SettingsDialog
          setup={setup}
          onClose={() => setDialog(null)}
          onPair={() => setDialog("pair")}
          onDevices={() => setDialog("devices")}
          onSaved={() => void refresh()}
        />
      )}
      {dialog === "pair" && <PairDialog onClose={() => setDialog(null)} />}
      {dialog === "devices" && <DevicesDialog onClose={() => setDialog(null)} />}
    </div>
  );
}

function NavButton({
  icon,
  label,
  count,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button className={active ? "nav-button active" : "nav-button"} onClick={onClick}>
      {icon}<span>{label}</span>{count ? <small>{count}</small> : null}
    </button>
  );
}

function AttachmentChip({ item, onRemove }: { item: Attachment; onRemove?: () => void }) {
  return (
    <div className="attachment-chip">
      <span>{attachmentIcon(item.kind)}</span>
      <div><strong>{item.name}</strong><small>{formatSize(item.size_bytes)}</small></div>
      {onRemove && <button onClick={onRemove} aria-label={`Remove ${item.name}`}><X size={14} /></button>}
    </div>
  );
}

function Composer({
  draft,
  pending,
  sending,
  uploading,
  textareaRef,
  fileRef,
  onDraft,
  onFiles,
  onRemove,
  onSend,
}: {
  draft: string;
  pending: Attachment[];
  sending: boolean;
  uploading: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  fileRef: React.RefObject<HTMLInputElement | null>;
  onDraft: (value: string) => void;
  onFiles: (files: FileList | File[]) => Promise<void>;
  onRemove: (id: string) => void;
  onSend: () => Promise<void>;
}) {
  return (
    <div className="composer-wrap">
      <div className="composer">
        {pending.length > 0 && (
          <div className="pending-files">
            {pending.map((item) => (
              <AttachmentChip
                item={item}
                onRemove={() => onRemove(item.attachment_id)}
                key={item.attachment_id}
              />
            ))}
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={draft}
          rows={1}
          placeholder={uploading ? "Uploading…" : "Message soki code"}
          onChange={(event) => onDraft(event.target.value)}
          onPaste={(event) => {
            if (event.clipboardData.files.length) void onFiles(event.clipboardData.files);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void onSend();
            }
          }}
        />
        <div className="composer-actions">
          <button className="attach-button" onClick={() => fileRef.current?.click()} aria-label="Add photos, video, or files">
            <Paperclip size={19} />
          </button>
          <span className="attachment-hint">Photos, video & files</span>
          <button
            className="send-button"
            disabled={sending || uploading || (!draft.trim() && !pending.length)}
            onClick={() => void onSend()}
            aria-label="Send"
          >
            <ArrowUp size={18} strokeWidth={2.6} />
          </button>
        </div>
        <input
          ref={fileRef}
          className="visually-hidden"
          type="file"
          multiple
          accept="image/*,video/*,audio/*,.pdf,.txt,.md,.csv,.json,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip"
          onChange={(event) => event.target.files && void onFiles(event.target.files)}
        />
      </div>
      <p>Soki can make mistakes. Review important work and trading decisions.</p>
    </div>
  );
}

function LibraryView({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="library-view">
      <header>
        <div><h1>{title}</h1><p>{description}</p></div>
        {action}
      </header>
      {children}
    </section>
  );
}

function EmptyLibrary({ icon, label }: { icon: React.ReactNode; label: string }) {
  return <div className="empty-library">{icon}<strong>{label}</strong></div>;
}

function DialogFrame({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header><h2>{title}</h2><button onClick={onClose}><X size={19} /></button></header>
        {children}
      </section>
    </div>
  );
}

function SettingsDialog({
  setup,
  onClose,
  onPair,
  onDevices,
  onSaved,
}: {
  setup: SetupStatus | null;
  onClose: () => void;
  onPair: () => void;
  onDevices: () => void;
  onSaved: () => void;
}) {
  const [url, setUrl] = useState(setup?.hermes.url ?? "");
  const [key, setKey] = useState("");
  const [model, setModel] = useState("hermes");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  return (
    <DialogFrame title="Settings" onClose={onClose}>
      <div className="dialog-body">
        <div className="setting-summary">
          <span className={setup?.hermes.verified ? "status-dot online" : "status-dot"} />
          <div><strong>Agent runtime</strong><small>{setup?.hermes.verified ? "Connected" : "Not connected"}</small></div>
        </div>
        <label>Runtime URL<input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="http://127.0.0.1:..." /></label>
        <label>API key<input type="password" value={key} onChange={(event) => setKey(event.target.value)} placeholder="••••••••" /></label>
        <label>Model<input value={model} onChange={(event) => setModel(event.target.value)} /></label>
        {error && <p className="field-error">{error}</p>}
        <button
          className="primary-button"
          disabled={saving || !url || !key}
          onClick={async () => {
            setSaving(true);
            setError("");
            try {
              await api.configureHermes(url, key, model);
              onSaved();
              onClose();
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : "Could not connect.");
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "Connecting…" : "Save connection"}
        </button>
        <div className="dialog-links">
          <button onClick={onPair}><Smartphone size={17} /> Pair a phone <ChevronRight size={16} /></button>
          <button onClick={onDevices}><MonitorCog size={17} /> Paired devices <ChevronRight size={16} /></button>
        </div>
      </div>
    </DialogFrame>
  );
}

function PairDialog({ onClose }: { onClose: () => void }) {
  const [pairing, setPairing] = useState<PairingSession | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api.createPairing(api.baseUrl.replace("127.0.0.1", window.location.hostname))
      .then((value) => live && setPairing(value))
      .catch((caught) => live && setError(caught instanceof Error ? caught.message : "Could not create a code."));
    return () => { live = false; };
  }, []);
  return (
    <DialogFrame title="Pair your phone" onClose={onClose}>
      <div className="pair-body">
        {pairing ? (
          <>
            <div className="qr-frame"><QRCodeSVG value={pairing.qr_payload} size={210} level="M" /></div>
            <h3>Scan with the Soki Android app</h3>
            <p>The code expires in five minutes and can only be used once.</p>
          </>
        ) : <div className="dialog-loading">{error || "Creating a secure code…"}</div>}
      </div>
    </DialogFrame>
  );
}

function DevicesDialog({ onClose }: { onClose: () => void }) {
  const [devices, setDevices] = useState<PairedDevice[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.devices().then(setDevices).catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load devices."));
  }, []);
  return (
    <DialogFrame title="Paired devices" onClose={onClose}>
      <div className="dialog-body">
        {error && <p className="field-error">{error}</p>}
        {devices.length ? devices.map((device) => (
          <div className="device-row" key={device.device_id}>
            <span><Smartphone size={18} /></span>
            <div><strong>{device.name}</strong><small>Seen {new Date(device.last_seen_at).toLocaleString()}</small></div>
            <button aria-label={`Remove ${device.name}`} onClick={async () => {
              await api.revokeDevice(device.device_id);
              setDevices((current) => current.filter((item) => item.device_id !== device.device_id));
            }}><Trash2 size={17} /></button>
          </div>
        )) : <EmptyLibrary icon={<Smartphone />} label="No paired phones" />}
      </div>
    </DialogFrame>
  );
}
