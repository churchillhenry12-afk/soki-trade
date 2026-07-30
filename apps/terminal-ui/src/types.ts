export type SystemStatus = {
  version: string;
  mode: string;
  runtime: "PRODUCTION" | "DEMO";
  uptime_seconds: number;
  hermes: IntegrationStatus;
  market_data: IntegrationStatus;
  mt5: IntegrationStatus;
  quantum: IntegrationStatus;
};

export type IntegrationStatus = {
  status: string;
  adapter_kind: string;
  verified: boolean;
  [key: string]: string | boolean;
};

export type SetupConnection = {
  configured?: boolean;
  connected?: boolean;
  last_error?: string;
  [key: string]: string | boolean | undefined;
};

export type SetupStatus = {
  agent: {
    name: string;
    ready: boolean;
    runtime: "PRODUCTION" | "DEMO";
    execution: string;
  };
  hermes?: IntegrationStatus & {
    configured?: boolean;
    url?: string;
    last_error?: string;
  };
  model: {
    provider: string;
    model: string;
    base_url: string;
    configured: boolean;
    connected: boolean;
    api_key_present: boolean;
  };
  market_data: IntegrationStatus;
  telegram: SetupConnection;
  mt5: SetupConnection;
};

export type ResearchObjective = {
  objective_id: string;
  title: string;
  thesis: string;
  symbols: string[];
  timeframe: string;
  created_at: string;
};

export type StrategyCondition = {
  indicator: string;
  period: number;
  comparison: string;
  target_indicator: string | null;
  target_period: number | null;
  value: number | null;
};

export type StrategyDefinition = {
  strategy_id: string;
  name: string;
  version: number;
  symbols: string[];
  timeframe: string;
  entry: {
    operator: string;
    conditions: StrategyCondition[];
  };
  exit: {
    stop_loss_atr: number;
    take_profit_atr: number;
    trailing_atr: number | null;
  };
  maximum_spread: number;
  risk: {
    risk_per_trade: number;
    maximum_concurrent_positions: number;
  };
  allowed_direction: string;
  generation_source: string;
};

export type MT5Status = {
  status: string;
  adapter_kind: string;
  verified: boolean;
  order_access: boolean;
  account_mode: string;
};

export type LocalMT5Status = {
  platform: string;
  installed: boolean;
  application_path: string;
  gateway_connected: boolean;
  account_mode: string;
  account_mode_source: string;
  read_only: boolean;
  bridge_required: boolean;
};

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
};

export type AgentChatResponse = {
  reply: string;
  action:
    | "MESSAGE"
    | "EXPERIMENT_STARTED"
    | "REPORT"
    | "STATUS"
    | "CONNECTION_SETUP"
    | "CONNECTION_CHANGED";
  client_action: "CONNECT_MODEL" | "CONNECT_TELEGRAM" | "CONNECT_MT5" | null;
  experiment_id: string | null;
  state: string | null;
  session_id: string | null;
  task_id: string | null;
  runtime: string;
  proof: AgentTask | null;
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
  created_at: string;
  updated_at: string;
};

export type ExperimentEvent = {
  event_id: string;
  sequence: number;
  timestamp: string;
  experiment_id: string;
  correlation_id: string;
  agent: string;
  event_type: string;
  state: string;
  status: string;
  payload: Record<string, unknown>;
};

export type Metrics = {
  net_return: number;
  annualized_return: number;
  maximum_drawdown: number;
  sharpe_ratio: number;
  profit_factor: number;
  number_of_trades: number;
  win_rate: number;
};

export type Backtest = {
  backtest_id: string;
  strategy_id: string;
  metrics: Metrics;
  equity_curve: number[];
};

export type StatisticalResult = {
  strategy_id: string;
  robustness_score: number;
  overfitting_risk: number;
  execution_realism_score: number;
  regime_stability_score: number;
  deployment_recommendation: string;
  rejection_reasons: string[];
};

export type SolverResult = {
  solver: string;
  solution: string[];
  objective_score: number;
  runtime_ms: number;
  iterations: number;
  verified: boolean;
};

export type SolverBenchmark = {
  problem: string;
  solvers: Record<string, SolverResult>;
  winner: string;
  validation_required: boolean;
};

export type RiskDecision = {
  eligible: boolean;
  approved: boolean;
  target_mode: string;
  checks: Record<string, boolean>;
  rejection_reasons: string[];
  rules_version: string;
};

export type FinalReport = {
  experiment_id: string;
  objective: {
    title: string;
    thesis: string;
    symbols: string[];
    timeframe: string;
  };
  strategies: StrategyDefinition[];
  backtests: Backtest[];
  statistical_results: StatisticalResult[];
  classical_selection: SolverResult;
  solver_benchmark: SolverBenchmark;
  risk_decision: RiskDecision;
};

export type Experiment = {
  experiment_id: string;
  objective_id: string;
  correlation_id?: string;
  parent_experiment_id?: string | null;
  state: string;
  status: string;
  created_at: string;
  updated_at?: string;
  report: FinalReport | null;
};
