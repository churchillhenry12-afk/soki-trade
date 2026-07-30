import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

class MockWebSocket {
  close = vi.fn();
}

const systemStatus = {
  version: "0.1.0",
  mode: "RESEARCH",
  runtime: "PRODUCTION",
  uptime_seconds: 2,
  hermes: { status: "READY", adapter_kind: "local-deterministic-research", verified: true },
  market_data: {
    status: "READY",
    adapter_kind: "yahoo-finance+local-cache",
    verified: true,
    source: "CACHE",
  },
  mt5: { status: "DISABLED", adapter_kind: "mt5-disabled-research-only", verified: true },
  quantum: {
    status: "DISABLED",
    adapter_kind: "classical-exhaustive-control",
    verified: false,
  },
};

const setupStatus = {
  agent: {
    name: "Soki Trade",
    ready: true,
    runtime: "PRODUCTION",
    execution: "RESEARCH_AND_PAPER_ONLY",
  },
  model: {
    provider: "local",
    model: "qwen2.5-coder:14b",
    base_url: "http://127.0.0.1:11434/v1",
    configured: true,
    connected: true,
    api_key_present: false,
  },
  market_data: systemStatus.market_data,
  telegram: { configured: false, connected: false },
  mt5: { configured: false, connected: false },
};

const objective = {
  objective_id: "objective-1",
  title: "EURUSD resilience",
  thesis: "Test execution resilience with deterministic spread stress.",
  symbols: ["EURUSD"],
  timeframe: "M15",
  created_at: "2026-07-26T10:00:00Z",
};

const strategy = {
  strategy_id: "EURUSD-M15-0001",
  name: "EMA execution candidate",
  version: 1,
  symbols: ["EURUSD"],
  timeframe: "M15",
  entry: {
    operator: "AND",
    conditions: [
      {
        indicator: "EMA",
        period: 8,
        comparison: "crosses_above",
        target_indicator: "EMA",
        target_period: 21,
        value: null,
      },
    ],
  },
  exit: { stop_loss_atr: 1.5, take_profit_atr: 2.25, trailing_atr: 1.2 },
  maximum_spread: 0.00035,
  risk: { risk_per_trade: 0.005, maximum_concurrent_positions: 1 },
  allowed_direction: "BOTH",
  generation_source: "LOCAL_ENGINE",
};

const backtest = {
  backtest_id: "backtest-1",
  strategy_id: strategy.strategy_id,
  seed: 42,
  metrics: {
    net_return: 0.08,
    annualized_return: 0.12,
    maximum_drawdown: 0.06,
    sharpe_ratio: 1.4,
    profit_factor: 1.3,
    number_of_trades: 120,
    win_rate: 0.55,
  },
  equity_curve: [100000, 100300, 101100, 108000],
};

const riskReview = {
  eligible: true,
  approved: false,
  target_mode: "PAPER",
  checks: {
    live_trading_disabled: true,
    portfolio_not_empty: true,
    stress_tests_passed: true,
    human_approval_present: false,
  },
  rejection_reasons: ["human_approval_present"],
  rules_version: "2026-01",
};

const experiment = {
  experiment_id: "experiment-1",
  objective_id: objective.objective_id,
  state: "AWAITING_HUMAN_APPROVAL",
  status: "RUNNING",
  created_at: "2026-07-26T10:01:00Z",
  updated_at: "2026-07-26T10:02:00Z",
  report: {
    experiment_id: "experiment-1",
    objective,
    strategies: [strategy],
    backtests: [backtest],
    statistical_results: [
      {
        strategy_id: strategy.strategy_id,
        robustness_score: 0.82,
        overfitting_risk: 0.18,
        execution_realism_score: 0.9,
        regime_stability_score: 0.85,
        deployment_recommendation: "PAPER",
        rejection_reasons: [],
      },
    ],
    classical_selection: {
      solver: "deterministic_ranked_subset",
      solution: [strategy.strategy_id],
      objective_score: 0.82,
      runtime_ms: 0.2,
      iterations: 1,
      verified: true,
    },
    solver_benchmark: {
      problem: "strategy_portfolio_selection",
      winner: "classical-exhaustive-control",
      validation_required: false,
      solvers: {
        "classical-exhaustive-control": {
          solver: "classical-exhaustive-control",
          solution: [strategy.strategy_id],
          objective_score: 0.84,
          runtime_ms: 0.4,
          iterations: 2,
          verified: true,
        },
      },
    },
    risk_decision: riskReview,
  },
};

afterEach(cleanup);

beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    clear: () => storage.clear(),
  });
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      let payload: unknown = systemStatus;
      if (url.endsWith("/setup/status")) payload = setupStatus;
      if (url.endsWith("/research/objectives")) payload = [objective];
      if (url.endsWith("/experiments")) payload = [experiment];
      if (url.endsWith("/strategies")) payload = [strategy];
      if (url.endsWith("/risk/reviews")) payload = [riskReview];
      if (url.endsWith("/mt5/status")) {
        payload = {
          status: "DISABLED",
          adapter_kind: "mt5-disabled-research-only",
          verified: true,
          order_access: false,
          account_mode: "NONE",
        };
      }
      if (url.endsWith("/mt5/local-status")) {
        payload = {
          platform: "darwin",
          installed: true,
          application_path: "/Applications/MetaTrader 5.app",
          gateway_connected: false,
          account_mode: "UNKNOWN",
          bridge_required: true,
        };
      }
      if (url.endsWith("/agent/chat")) {
        payload = {
          reply: "I can **connect Telegram** now. Enter the secure details below.",
          action: "CONNECTION_SETUP",
          client_action: "CONNECT_TELEGRAM",
          experiment_id: null,
          state: null,
        };
      }
      if (url.endsWith("/gateways/telegram/connect")) {
        payload = {
          configured: true,
          connected: true,
          inbound_ready: true,
          bot_username: "soki_bot",
        };
      }
      if (url.endsWith("/gateways/mt5/connect")) {
        payload = {
          configured: true,
          connected: true,
          account_mode: "REAL",
          account_mode_source: "USER_SELECTED",
          read_only: true,
        };
      }
      if (url.endsWith("/models/scan")) {
        payload = {
          provider: "local",
          base_url: "http://127.0.0.1:11434/v1",
          count: 2,
          models: ["qwen2.5-coder:14b", "qwen3:8b"],
        };
      }
      return Promise.resolve({
        ok: true,
        json: async () => payload,
        requestBody: init?.body,
      });
    }),
  );
});

test("starts with honest connection setup and opens the agent chat", async () => {
  render(<App />);

  expect(await screen.findByText("Soky Code is ready to work.")).toBeInTheDocument();
  expect(screen.getByText("Market data")).toBeInTheDocument();
  expect(screen.getAllByText("Not connected")).toHaveLength(2);

  fireEvent.click(screen.getByRole("button", { name: /Open Soky Code/ }));

  await waitFor(() => {
    expect(screen.getByPlaceholderText("Give Soky Code a task…")).toBeInTheDocument();
  });
  expect(screen.getByText("What outcome do you need?")).toBeInTheDocument();
  expect(screen.queryByText("DASHBOARD")).not.toBeInTheDocument();
});

test("shows the verified terminal installer when the local agent is offline", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Failed to fetch"))));

  render(<App />);

  expect(
    await screen.findByText("Connect this interface to your Soky agent"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "curl -fsSL https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/install.sh | bash",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "irm https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/install.ps1 | iex",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "PowerShell installer" })).toHaveAttribute(
    "href",
    "https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/install.ps1",
  );
  expect(screen.getByRole("link", { name: "Shell installer" })).toHaveAttribute(
    "href",
    "https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/install.sh",
  );
});

test("scans the provider before offering available models", async () => {
  render(<App />);

  await screen.findByText("Soky Code is ready to work.");
  fireEvent.click(screen.getByRole("button", { name: "Scan available models" }));

  expect(await screen.findByText("qwen3:8b")).toBeInTheDocument();
  expect(
    screen.getByText("Found 2 available models. Choose one, then save and test."),
  ).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/models/scan",
    expect.objectContaining({ method: "POST" }),
  );
});

test("lets the user connect a demo or read-only real MT5 account", async () => {
  render(<App />);

  await screen.findByText("Soky Code is ready to work.");
  fireEvent.change(screen.getByLabelText("Account type"), {
    target: { value: "REAL" },
  });
  fireEvent.change(screen.getByLabelText("Gateway URL"), {
    target: { value: "http://127.0.0.1:8765" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Connect MT5 bridge" }));

  expect(
    await screen.findByText("The MT5 REAL account is connected in read-only mode."),
  ).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/gateways/mt5/connect",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        transport: "rest",
        endpoint: "http://127.0.0.1:8765",
        account_mode: "REAL",
        token: null,
      }),
    }),
  );
});

test("opens a real Telegram connection tool inside agent chat", async () => {
  render(<App />);

  await screen.findByText("Soky Code is ready to work.");
  fireEvent.click(screen.getByRole("button", { name: /Open Soky Code/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Connect Telegram" }));

  expect(await screen.findByText("connect Telegram", { selector: "strong" })).toBeInTheDocument();
  const telegramTool = await screen.findByRole("article", { name: "Connect Telegram" });
  expect(telegramTool).toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText("Token from @BotFather"), {
    target: { value: "123456:test-token" },
  });
  fireEvent.change(screen.getByPlaceholderText("Only this chat can control Soky"), {
    target: { value: "12345" },
  });
  fireEvent.click(within(telegramTool).getByRole("button", { name: "Connect Telegram" }));

  expect(await screen.findByText(/Telegram is connected as @soki_bot/)).toBeInTheDocument();
});

test("every product section opens with real API-backed content", async () => {
  render(<App />);

  await screen.findByText("Soky Code is ready to work.");
  fireEvent.click(screen.getByRole("button", { name: /Open Soky Code/ }));

  fireEvent.click(await screen.findByRole("button", { name: "F1 Overview" }));
  expect(await screen.findByText("One agent. Every control surface.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "F3 Research" }));
  expect(await screen.findByText("Create a real strategy study")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "F4 Runs" }));
  expect(await screen.findByText("Experiments and live evidence")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "F5 Strategies" }));
  expect(await screen.findByText("Validated DSL and deterministic backtests")).toBeInTheDocument();
  expect(screen.getByText("EMA execution candidate")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "F6 Labs" }));
  expect(await screen.findByText("Classical control before quantum claims")).toBeInTheDocument();
  expect(screen.queryByText("EMA execution candidate")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "F7 Risk" }));
  expect(await screen.findByText("Deterministic rules agents cannot override")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "F8 Connections" }));
  expect(
    await screen.findByText("Installed software is not the same as a verified gateway"),
  ).toBeInTheDocument();
  expect(screen.getByText("/Applications/MetaTrader 5.app")).toBeInTheDocument();
});
