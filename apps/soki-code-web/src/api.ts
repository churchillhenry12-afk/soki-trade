import type {
  AgentChatResponse,
  AgentTask,
  Attachment,
  HermesStatus,
  PairedDevice,
  PairingSession,
  SetupStatus,
} from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isForm = options?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string | { message?: string } }
      | null;
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : payload?.detail?.message ?? `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE,

  setup: () => request<SetupStatus>("/setup/status"),

  tasks: () => request<AgentTask[]>("/agent/tasks?limit=12"),

  chat: (
    message: string,
    sessionId: string,
    history: Array<{ role: "user" | "assistant"; content: string }>,
    attachmentIds: string[] = [],
  ) =>
    request<AgentChatResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId,
        history: history.slice(-12),
        attachment_ids: attachmentIds,
      }),
    }),

  attachments: () => request<Attachment[]>("/attachments"),

  uploadAttachment: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Attachment>("/attachments", { method: "POST", body });
  },

  configureHermes: (url: string, apiKey: string, model: string) =>
    request<HermesStatus>("/hermes/config", {
      method: "POST",
      body: JSON.stringify({
        url,
        api_key: apiKey,
        model,
        persist: true,
      }),
    }),

  testHermes: () => request<HermesStatus>("/hermes/test", { method: "POST" }),

  createPairing: (apiBaseUrl: string) =>
    request<PairingSession>("/pairing/sessions", {
      method: "POST",
      body: JSON.stringify({ api_base_url: apiBaseUrl }),
    }),

  pairingStatus: (pairingId: string) =>
    request<{ status: "WAITING" | "PAIRED" | "EXPIRED"; device_id?: string }>(
      `/pairing/sessions/${pairingId}`,
    ),

  devices: () => request<PairedDevice[]>("/devices"),

  revokeDevice: (deviceId: string) =>
    request<{ revoked: boolean }>(`/devices/${deviceId}`, { method: "DELETE" }),
};
