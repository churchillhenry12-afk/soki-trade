import type {
  AgentChatResponse,
  ChatTurn,
  Experiment,
  ExperimentEvent,
  LocalMT5Status,
  MT5Status,
  ResearchObjective,
  RiskDecision,
  SetupConnection,
  SetupStatus,
  SolverBenchmark,
  SolverResult,
  StrategyDefinition,
  SystemStatus,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
export const WS_BASE = API_BASE.replace(/^http/, "ws");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string"
      ? body.detail
      : body?.detail
        ? JSON.stringify(body.detail)
        : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () => request<SystemStatus>("/system/status"),
  setupStatus: () => request<SetupStatus>("/setup/status"),
  configureModel: (body: {
    provider: string;
    model: string;
    base_url: string;
    api_key: string | null;
  }) =>
    request<SetupStatus["model"]>("/models/config", {
      method: "POST",
      body: JSON.stringify({ ...body, persist: true }),
    }),
  scanModels: (body: {
    provider: string;
    base_url: string;
    api_key: string | null;
  }) =>
    request<{ provider: string; base_url: string; count: number; models: string[] }>(
      "/models/scan",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  testModel: () =>
    request<SetupStatus["model"]>("/models/test", {
      method: "POST",
    }),
  connectTelegram: (body: { bot_token: string; chat_id: string }) =>
    request<SetupConnection>("/gateways/telegram/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  disconnectTelegram: () =>
    request<SetupConnection>("/gateways/telegram", {
      method: "DELETE",
    }),
  connectMT5: (body: {
    transport: "rest" | "mcp";
    endpoint: string;
    account_mode: "DEMO" | "REAL";
    token: string | null;
  }) =>
    request<SetupConnection>("/gateways/mt5/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  disconnectMT5: () =>
    request<SetupConnection>("/gateways/mt5", {
      method: "DELETE",
    }),
  agentChat: (body: {
    message: string;
    history: ChatTurn[];
    experiment_id: string | null;
    session_id: string;
  }) =>
    request<AgentChatResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  objectives: () => request<ResearchObjective[]>("/research/objectives"),
  experiments: () => request<Experiment[]>("/experiments"),
  strategies: () => request<StrategyDefinition[]>("/strategies"),
  riskReviews: () => request<RiskDecision[]>("/risk/reviews"),
  experiment: (id: string) => request<Experiment>(`/experiments/${id}`),
  experimentEvents: (id: string) =>
    request<ExperimentEvent[]>(`/experiments/${id}/events`),
  optimization: (id: string) =>
    request<SolverResult>(`/optimizations/${id}`),
  quantumBenchmark: (id: string) =>
    request<SolverBenchmark>(`/quantum/jobs/${id}`),
  mt5Status: () => request<MT5Status>("/mt5/status"),
  localMT5Status: () => request<LocalMT5Status>("/mt5/local-status"),
  directBacktest: (experimentId: string, strategyId: string) =>
    request<NonNullable<Experiment["report"]>["backtests"][number]>("/backtests", {
      method: "POST",
      body: JSON.stringify({
        experiment_id: experimentId,
        strategy_id: strategyId,
        seed: 42,
      }),
    }),
  createObjective: (body: {
    title: string;
    thesis: string;
    symbols: string[];
    timeframe: string;
  }) =>
    request<{ objective_id: string }>("/research/objectives", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createExperiment: (objectiveId: string) =>
    request<Experiment>("/experiments", {
      method: "POST",
      body: JSON.stringify({ objective_id: objectiveId, seed: 42 }),
    }),
  startExperiment: (id: string) =>
    request<Experiment>(`/experiments/${id}/start`, { method: "POST" }),
  controlExperiment: (id: string, action: "pause" | "resume" | "cancel") =>
    request<Experiment>(`/experiments/${id}/${action}`, { method: "POST" }),
  approvePaper: (id: string, approver: string) =>
    request<Experiment>("/approvals", {
      method: "POST",
      body: JSON.stringify({
        experiment_id: id,
        approver,
        target_mode: "PAPER",
        acknowledged_no_live_trading: true,
      }),
    }),
};
