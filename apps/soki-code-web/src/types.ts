export type HermesStatus = {
  status: string;
  adapter_kind: string;
  configured: boolean;
  verified: boolean;
  url: string;
  last_error: string;
};

export type SetupStatus = {
  agent: {
    name: string;
    ready: boolean;
    runtime: string;
    execution: string;
    proof_loop: string;
  };
  hermes: HermesStatus;
  market_data: Record<string, string | boolean>;
  telegram: Record<string, string | boolean>;
  mt5: Record<string, string | boolean>;
};

export type ProofCheck = {
  key: string;
  label: string;
  status: "PENDING" | "RUNNING" | "VERIFIED" | "FAILED";
  evidence: string;
};

export type AgentTask = {
  task_id: string;
  session_id: string;
  request: string;
  status: "RUNNING" | "WAITING" | "VERIFIED" | "FAILED";
  runtime: string;
  checks: ProofCheck[];
  response: string;
  error: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  task?: AgentTask;
  runtime?: string;
  attachments?: Attachment[];
};

export type AgentChatResponse = {
  reply: string;
  action: string;
  session_id: string;
  task_id: string;
  runtime: string;
  proof?: AgentTask;
};

export type PairingSession = {
  pairing_id: string;
  expires_at: string;
  qr_payload: string;
};

export type PairedDevice = {
  device_id: string;
  name: string;
  created_at: string;
  last_seen_at: string;
};

export type Attachment = {
  attachment_id: string;
  name: string;
  media_type: string;
  kind: "IMAGE" | "VIDEO" | "AUDIO" | "DOCUMENT" | "ARCHIVE" | "OTHER";
  size_bytes: number;
  sha256: string;
  created_at: string;
  download_url: string;
};
