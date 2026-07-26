import { useCallback, useEffect, useRef, useState } from "react";
import { api, WS_BASE } from "./api";
import type {
  AgentChatResponse,
  ChatTurn,
  Experiment,
  ExperimentEvent,
  SystemStatus,
} from "./types";

const TERMINAL_STATES = new Set([
  "AWAITING_HUMAN_APPROVAL",
  "REJECTED",
  "FAILED",
  "CANCELLED",
  "COMPLETED",
]);

export function useQForge() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [events, setEvents] = useState<ExperimentEvent[]>([]);
  const [connection, setConnection] = useState<"OFFLINE" | "CONNECTING" | "LIVE">("OFFLINE");
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    void api.status().then(setStatus).catch((reason: Error) => setError(reason.message));
    const timer = window.setInterval(() => {
      void api.status().then(setStatus).catch(() => undefined);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, []);

  const refreshExperiment = useCallback(async (id: string) => {
    const current = await api.experiment(id);
    setExperiment(current);
  }, []);

  const connect = useCallback(
    (id: string) => {
      socketRef.current?.close();
      setConnection("CONNECTING");
      const socket = new WebSocket(`${WS_BASE}/ws/experiments/${id}`);
      socketRef.current = socket;
      socket.onopen = () => setConnection("LIVE");
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data as string) as ExperimentEvent;
        setEvents((current) => {
          if (current.some((item) => item.event_id === event.event_id)) return current;
          return [...current, event].slice(-240);
        });
        if (TERMINAL_STATES.has(event.state)) {
          void refreshExperiment(id);
        }
      };
      socket.onerror = () => setError("WebSocket stream interrupted");
      socket.onclose = () => setConnection("OFFLINE");
    },
    [refreshExperiment],
  );

  useEffect(() => () => socketRef.current?.close(), []);

  const selectExperiment = useCallback(
    async (id: string) => {
      setError(null);
      socketRef.current?.close();
      const [current, history] = await Promise.all([
        api.experiment(id),
        api.experimentEvents(id),
      ]);
      setExperiment(current);
      setEvents(history.slice(-240));
      if (TERMINAL_STATES.has(current.state)) {
        setConnection("OFFLINE");
      } else {
        connect(id);
      }
    },
    [connect],
  );

  const launch = useCallback(
    async (input: { title: string; thesis: string; symbol: string; timeframe: string }) => {
      setError(null);
      setEvents([]);
      const objective = await api.createObjective({
        title: input.title,
        thesis: input.thesis,
        symbols: [input.symbol],
        timeframe: input.timeframe,
      });
      const created = await api.createExperiment(objective.objective_id);
      setExperiment(created);
      connect(created.experiment_id);
      await api.startExperiment(created.experiment_id);
      await refreshExperiment(created.experiment_id);
    },
    [connect, refreshExperiment],
  );

  const control = useCallback(
    async (action: "pause" | "resume" | "cancel") => {
      if (!experiment) return;
      await api.controlExperiment(experiment.experiment_id, action);
      await refreshExperiment(experiment.experiment_id);
    },
    [experiment, refreshExperiment],
  );

  const approvePaper = useCallback(
    async (approver: string) => {
      if (!experiment) return;
      const approved = await api.approvePaper(experiment.experiment_id, approver);
      setExperiment(approved);
    },
    [experiment],
  );

  const chat = useCallback(
    async (message: string, history: ChatTurn[]): Promise<AgentChatResponse> => {
      setError(null);
      const response = await api.agentChat({
        message,
        history,
        experiment_id: experiment?.experiment_id ?? null,
      });
      if (response.experiment_id && response.action === "EXPERIMENT_STARTED") {
        setEvents([]);
        const current = await api.experiment(response.experiment_id);
        setExperiment(current);
        connect(response.experiment_id);
      }
      if (response.experiment_id && response.action !== "EXPERIMENT_STARTED") {
        await refreshExperiment(response.experiment_id);
      }
      return response;
    },
    [connect, experiment?.experiment_id, refreshExperiment],
  );

  return {
    status,
    experiment,
    events,
    connection,
    error,
    launch,
    control,
    approvePaper,
    chat,
    selectExperiment,
  };
}
