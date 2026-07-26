import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import type {
  Backtest,
  Experiment,
  LocalMT5Status,
  MT5Status,
  ResearchObjective,
  RiskDecision,
  SetupStatus,
  StrategyDefinition,
} from "../types";
import type { useQForge as useQForgeHook } from "../useQForge";
import { CommandTerminal } from "./CommandTerminal";
import { EquityChart } from "./EquityChart";
import { Workflow } from "./Workflow";

export type ProductSection =
  | "overview"
  | "agent"
  | "research"
  | "runs"
  | "strategies"
  | "labs"
  | "risk"
  | "connections";

type QForgeController = ReturnType<typeof useQForgeHook>;

type Props = {
  section: Exclude<ProductSection, "agent">;
  setup: SetupStatus;
  qforge: QForgeController;
  onManageSetup: () => void;
  onOpenAgent: () => void;
  onRefreshSetup: () => Promise<void>;
};

type Inventory = {
  objectives: ResearchObjective[];
  experiments: Experiment[];
  strategies: StrategyDefinition[];
  riskReviews: RiskDecision[];
  mt5: MT5Status | null;
  localMT5: LocalMT5Status | null;
};

const EMPTY_INVENTORY: Inventory = {
  objectives: [],
  experiments: [],
  strategies: [],
  riskReviews: [],
  mt5: null,
  localMT5: null,
};

function formatDate(value: string | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function stateTone(state: string) {
  if (["FAILED", "REJECTED", "CANCELLED"].includes(state)) return "danger";
  if (["COMPLETED", "APPROVED_FOR_PAPER", "APPROVED_FOR_DEMO"].includes(state)) return "ready";
  if (state === "AWAITING_HUMAN_APPROVAL") return "attention";
  return "active";
}

function SectionHeader({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <header className="ops-section__header">
      <div>
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
      {action ? <div className="ops-section__action">{action}</div> : null}
    </header>
  );
}

function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="ops-empty">
      <span>NO DATA</span>
      <strong>{title}</strong>
      <p>{detail}</p>
      {action}
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <div className="ops-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

export function OperationsCenter({
  section,
  setup,
  qforge,
  onManageSetup,
  onOpenAgent,
  onRefreshSetup,
}: Props) {
  const [inventory, setInventory] = useState<Inventory>(EMPTY_INVENTORY);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [backtestResult, setBacktestResult] = useState<Backtest | null>(null);
  const [backtestBusy, setBacktestBusy] = useState(false);
  const [approvalName, setApprovalName] = useState("");
  const [approvalBusy, setApprovalBusy] = useState(false);

  const refreshInventory = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [objectives, experiments, strategies, riskReviews, mt5, localMT5] =
        await Promise.all([
          api.objectives(),
          api.experiments(),
          api.strategies(),
          api.riskReviews(),
          api.mt5Status(),
          api.localMT5Status(),
        ]);
      setInventory({ objectives, experiments, strategies, riskReviews, mt5, localMT5 });
      setSelectedStrategyId((current) => current || strategies[0]?.strategy_id || "");
    } catch (error) {
      setLoadError((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshInventory();
  }, [refreshInventory, qforge.experiment?.updated_at]);

  const currentExperiment = qforge.experiment ?? inventory.experiments[0] ?? null;
  const report = currentExperiment?.report ?? null;
  const catalogStrategies = useMemo(() => {
    if (report?.strategies.length) return report.strategies;

    const seen = new Set<string>();
    return inventory.strategies.filter((strategy) => {
      if (seen.has(strategy.strategy_id)) return false;
      seen.add(strategy.strategy_id);
      return true;
    });
  }, [inventory.strategies, report]);
  const selectedStrategy =
    catalogStrategies.find((item) => item.strategy_id === selectedStrategyId) ??
    catalogStrategies[0] ??
    null;
  const selectedReportBacktest =
    report?.backtests.find((item) => item.strategy_id === selectedStrategy?.strategy_id) ?? null;
  const bestStat = useMemo(() => {
    if (!report) return null;
    return [...report.statistical_results].sort(
      (left, right) => right.robustness_score - left.robustness_score,
    )[0];
  }, [report]);
  const bestBacktest =
    report?.backtests.find((item) => item.strategy_id === bestStat?.strategy_id) ?? null;

  async function runDirectBacktest() {
    if (!currentExperiment || !selectedStrategy) return;
    setBacktestBusy(true);
    setBacktestResult(null);
    try {
      setBacktestResult(
        await api.directBacktest(
          currentExperiment.experiment_id,
          selectedStrategy.strategy_id,
        ),
      );
    } finally {
      setBacktestBusy(false);
    }
  }

  async function approvePaper() {
    if (!approvalName.trim()) return;
    setApprovalBusy(true);
    try {
      await qforge.approvePaper(approvalName.trim());
      await refreshInventory();
    } finally {
      setApprovalBusy(false);
    }
  }

  if (loadError) {
    return (
      <section className="ops-section">
        <SectionHeader
          eyebrow="Operations data"
          title="The control center could not load"
          detail="The agent remains available, but this section needs the API inventory."
        />
        <EmptyState
          title="API inventory unavailable"
          detail={loadError}
          action={<button onClick={() => void refreshInventory()}>Retry section</button>}
        />
      </section>
    );
  }

  if (section === "overview") {
    return (
      <section className="ops-section" data-testid="section-overview">
        <SectionHeader
          eyebrow="Command overview"
          title="One agent. Every control surface."
          detail="Live system state, the latest deterministic research run, and the boundaries that remain locked."
          action={<button onClick={onOpenAgent}>Ask Soki</button>}
        />
        <div className="ops-metric-grid">
          <Metric
            label="Agent"
            value={setup.agent.ready ? "ONLINE" : "SETUP"}
            detail={setup.model.model}
          />
          <Metric
            label="Market data"
            value={setup.market_data.status}
            detail={String(setup.market_data.source ?? "public feed")}
          />
          <Metric
            label="Research runs"
            value={inventory.experiments.length}
            detail={`${inventory.objectives.length} objectives`}
          />
          <Metric
            label="Execution"
            value="LOCKED"
            detail="Research and paper only"
          />
        </div>
        <div className="ops-grid ops-grid--overview">
          <article className="ops-card ops-card--wide">
            <div className="ops-card__heading">
              <div><span>PIPELINE</span><h2>Latest research workflow</h2></div>
              {currentExperiment ? (
                <em className={`ops-state ops-state--${stateTone(currentExperiment.state)}`}>
                  {currentExperiment.state}
                </em>
              ) : null}
            </div>
            {currentExperiment ? (
              <Workflow state={currentExperiment.state} events={qforge.events} />
            ) : (
              <EmptyState
                title="No research run yet"
                detail="Create an objective and Soki will stream each deterministic stage here."
              />
            )}
          </article>
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>INTEGRATIONS</span><h2>Connection truth</h2></div>
            </div>
            <div className="ops-status-list">
              {[
                ["AI model", setup.model.connected, setup.model.model],
                ["Telegram", Boolean(setup.telegram.inbound_ready), String(setup.telegram.bot_username || "Not connected")],
                ["MT5 bridge", Boolean(setup.mt5.connected), String(setup.mt5.account_mode || "Not connected")],
                ["Live orders", false, "Disabled by policy"],
              ].map(([label, ready, detail]) => (
                <div key={String(label)}>
                  <i className={ready ? "is-ready" : ""} />
                  <span><strong>{String(label)}</strong><small>{String(detail)}</small></span>
                  <em>{ready ? "ready" : "off"}</em>
                </div>
              ))}
            </div>
          </article>
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>LATEST EVIDENCE</span><h2>Research outcome</h2></div>
            </div>
            {bestStat && bestBacktest ? (
              <>
                <div className="ops-outcome">
                  <strong>{bestStat.strategy_id}</strong>
                  <span>{bestStat.deployment_recommendation}</span>
                </div>
                <div className="ops-mini-metrics">
                  <Metric label="Return" value={formatPercent(bestBacktest.metrics.net_return)} />
                  <Metric label="Drawdown" value={formatPercent(bestBacktest.metrics.maximum_drawdown)} />
                  <Metric label="Robustness" value={bestStat.robustness_score.toFixed(3)} />
                </div>
              </>
            ) : (
              <EmptyState
                title="No completed evidence"
                detail="Run a study to populate backtests, robustness scores, and risk decisions."
              />
            )}
          </article>
        </div>
      </section>
    );
  }

  if (section === "research") {
    return (
      <section className="ops-section" data-testid="section-research">
        <SectionHeader
          eyebrow="Research desk"
          title="Create a real strategy study"
          detail="The objective becomes typed strategy DSL, real-data backtests, hostile execution tests, optimization, and deterministic risk review."
        />
        <div className="ops-grid ops-grid--research">
          <article className="ops-card ops-card--wide">
            <div className="ops-card__heading">
              <div><span>NEW OBJECTIVE</span><h2>Adversarial study</h2></div>
            </div>
            <CommandTerminal
              disabled={!setup.agent.ready}
              onLaunch={async (input) => {
                await qforge.launch(input);
                await refreshInventory();
              }}
            />
          </article>
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>OBJECTIVES</span><h2>Research archive</h2></div>
              <em>{inventory.objectives.length}</em>
            </div>
            <div className="ops-record-list">
              {inventory.objectives.slice(0, 12).map((objective) => (
                <div key={objective.objective_id}>
                  <span>{objective.symbols.join(", ")} · {objective.timeframe}</span>
                  <strong>{objective.title}</strong>
                  <p>{objective.thesis}</p>
                  <small>{formatDate(objective.created_at)}</small>
                </div>
              ))}
            </div>
          </article>
        </div>
      </section>
    );
  }

  if (section === "runs") {
    return (
      <section className="ops-section" data-testid="section-runs">
        <SectionHeader
          eyebrow="Run control"
          title="Experiments and live evidence"
          detail="Select any persisted experiment, inspect its event history, and control active state-machine runs."
          action={<button onClick={() => void refreshInventory()}>Refresh runs</button>}
        />
        <div className="ops-grid ops-grid--runs">
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>RUN INDEX</span><h2>Persisted experiments</h2></div>
              <em>{inventory.experiments.length}</em>
            </div>
            <div className="ops-run-list">
              {inventory.experiments.slice(0, 30).map((experiment) => (
                <button
                  className={
                    currentExperiment?.experiment_id === experiment.experiment_id
                      ? "is-selected"
                      : ""
                  }
                  key={experiment.experiment_id}
                  onClick={() => void qforge.selectExperiment(experiment.experiment_id)}
                >
                  <span>{experiment.experiment_id.slice(0, 8)}</span>
                  <strong>{experiment.report?.objective.title ?? "Research experiment"}</strong>
                  <em className={`ops-state ops-state--${stateTone(experiment.state)}`}>
                    {experiment.state}
                  </em>
                  <small>{formatDate(experiment.created_at)}</small>
                </button>
              ))}
            </div>
          </article>
          <article className="ops-card ops-card--wide">
            <div className="ops-card__heading">
              <div><span>EVENT STREAM</span><h2>{currentExperiment?.experiment_id.slice(0, 8) ?? "No run selected"}</h2></div>
              <div className="ops-control-row">
                <button
                  disabled={!currentExperiment || ["REJECTED", "FAILED", "CANCELLED", "COMPLETED"].includes(currentExperiment.state)}
                  onClick={() => void qforge.control("pause")}
                >
                  Pause
                </button>
                <button
                  disabled={currentExperiment?.state !== "PAUSED"}
                  onClick={() => void qforge.control("resume")}
                >
                  Resume
                </button>
                <button
                  disabled={!currentExperiment || ["REJECTED", "FAILED", "CANCELLED", "COMPLETED"].includes(currentExperiment.state)}
                  onClick={() => void qforge.control("cancel")}
                >
                  Cancel
                </button>
              </div>
            </div>
            {currentExperiment ? (
              <>
                <Workflow state={currentExperiment.state} events={qforge.events} />
                <div className="ops-event-log">
                  {qforge.events.slice(-40).reverse().map((event) => (
                    <div key={event.event_id}>
                      <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
                      <strong>{event.agent.replaceAll("_", " ")}</strong>
                      <span>{event.event_type}</span>
                      <em>{event.state}</em>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState title="Select a run" detail="Choose a persisted experiment to load its complete event history." />
            )}
          </article>
        </div>
      </section>
    );
  }

  if (section === "strategies") {
    const visibleBacktest = backtestResult ?? selectedReportBacktest;
    return (
      <section className="ops-section" data-testid="section-strategies">
        <SectionHeader
          eyebrow="Strategy evidence"
          title="Validated DSL and deterministic backtests"
          detail="Every candidate is structured data. Calculations come from Python services, never from the language model."
        />
        <div className="ops-grid ops-grid--strategies">
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>CATALOG</span><h2>Strategy definitions</h2></div>
              <em>{catalogStrategies.length}</em>
            </div>
            <div className="ops-strategy-list">
              {catalogStrategies.map((strategy) => (
                <button
                  className={selectedStrategy?.strategy_id === strategy.strategy_id ? "is-selected" : ""}
                  key={strategy.strategy_id}
                  onClick={() => {
                    setSelectedStrategyId(strategy.strategy_id);
                    setBacktestResult(null);
                  }}
                >
                  <span>{strategy.strategy_id}</span>
                  <strong>{strategy.name}</strong>
                  <small>{strategy.symbols.join(", ")} · {strategy.timeframe} · {strategy.generation_source}</small>
                </button>
              ))}
            </div>
          </article>
          <article className="ops-card ops-card--wide">
            {selectedStrategy ? (
              <>
                <div className="ops-card__heading">
                  <div><span>DSL INSPECTOR</span><h2>{selectedStrategy.strategy_id}</h2></div>
                  <button
                    disabled={
                      backtestBusy ||
                      !currentExperiment?.report?.strategies.some(
                        (item) => item.strategy_id === selectedStrategy.strategy_id,
                      )
                    }
                    onClick={() => void runDirectBacktest()}
                  >
                    {backtestBusy ? "Running…" : "Rerun backtest"}
                  </button>
                </div>
                <div className="ops-dsl">
                  <div>
                    <span>Entry logic</span>
                    {selectedStrategy.entry.conditions.map((condition) => (
                      <code key={`${condition.indicator}-${condition.period}`}>
                        {condition.indicator}({condition.period}) {condition.comparison.replaceAll("_", " ")}{" "}
                        {condition.target_indicator
                          ? `${condition.target_indicator}(${condition.target_period})`
                          : condition.value}
                      </code>
                    ))}
                  </div>
                  <dl>
                    <div><dt>Stop</dt><dd>{selectedStrategy.exit.stop_loss_atr} ATR</dd></div>
                    <div><dt>Target</dt><dd>{selectedStrategy.exit.take_profit_atr} ATR</dd></div>
                    <div><dt>Risk/trade</dt><dd>{formatPercent(selectedStrategy.risk.risk_per_trade)}</dd></div>
                    <div><dt>Direction</dt><dd>{selectedStrategy.allowed_direction}</dd></div>
                  </dl>
                </div>
                {visibleBacktest ? (
                  <>
                    <div className="ops-mini-metrics ops-mini-metrics--four">
                      <Metric label="Net return" value={formatPercent(visibleBacktest.metrics.net_return)} />
                      <Metric label="Max drawdown" value={formatPercent(visibleBacktest.metrics.maximum_drawdown)} />
                      <Metric label="Sharpe" value={visibleBacktest.metrics.sharpe_ratio.toFixed(2)} />
                      <Metric label="Trades" value={visibleBacktest.metrics.number_of_trades} />
                    </div>
                    <EquityChart values={visibleBacktest.equity_curve} />
                  </>
                ) : (
                  <EmptyState
                    title="No matching backtest in the selected run"
                    detail="Select a strategy from the current report to rerun its deterministic backtest."
                  />
                )}
              </>
            ) : (
              <EmptyState title="No strategies found" detail="Run a research objective to generate validated strategy definitions." />
            )}
          </article>
        </div>
      </section>
    );
  }

  if (section === "labs") {
    const benchmark = report?.solver_benchmark;
    return (
      <section className="ops-section" data-testid="section-labs">
        <SectionHeader
          eyebrow="Optimization lab"
          title="Classical control before quantum claims"
          detail="Solver results are benchmarked on the same portfolio problem. Disabled backends remain explicitly disabled."
        />
        <div className="ops-grid ops-grid--labs">
          <article className="ops-card ops-card--wide">
            <div className="ops-card__heading">
              <div><span>SOLVER BENCHMARK</span><h2>{benchmark?.problem.replaceAll("_", " ") ?? "No completed benchmark"}</h2></div>
              {benchmark ? <em>Winner · {benchmark.winner}</em> : null}
            </div>
            {benchmark ? (
              <div className="ops-solver-table">
                <div className="ops-solver-table__head">
                  <span>Solver</span><span>Score</span><span>Runtime</span><span>Iterations</span><span>Verified</span>
                </div>
                {Object.values(benchmark.solvers).map((solver) => (
                  <div key={solver.solver}>
                    <strong>{solver.solver}</strong>
                    <span>{solver.objective_score.toFixed(4)}</span>
                    <span>{solver.runtime_ms.toFixed(3)} ms</span>
                    <span>{solver.iterations}</span>
                    <em>{solver.verified ? "yes" : "no"}</em>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No solver evidence" detail="Complete a research run to generate classical and control benchmark results." />
            )}
          </article>
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>QUANTUM BACKEND</span><h2>{qforge.status?.quantum.status ?? "UNKNOWN"}</h2></div>
            </div>
            <div className="ops-integration-proof">
              <strong>{qforge.status?.quantum.adapter_kind ?? "No backend"}</strong>
              <p>
                {qforge.status?.quantum.verified
                  ? "The selected backend is verified for this runtime."
                  : "No QPU or QPanda claim is active. The verified classical exhaustive control remains the comparison baseline."}
              </p>
              <dl>
                <div><dt>Hardware claim</dt><dd>None</dd></div>
                <div><dt>Live execution</dt><dd>Disabled</dd></div>
                <div><dt>Validation required</dt><dd>{benchmark?.validation_required ? "Yes" : "No"}</dd></div>
              </dl>
            </div>
          </article>
        </div>
      </section>
    );
  }

  if (section === "risk") {
    const decision = report?.risk_decision ?? inventory.riskReviews[0] ?? null;
    return (
      <section className="ops-section" data-testid="section-risk">
        <SectionHeader
          eyebrow="Risk governor"
          title="Deterministic rules agents cannot override"
          detail="A human acknowledgement can complete an eligible paper export. It cannot convert a failed risk review into approval."
        />
        <div className="ops-grid ops-grid--risk">
          <article className="ops-card ops-card--wide">
            <div className="ops-card__heading">
              <div><span>CURRENT REVIEW</span><h2>{decision ? (decision.eligible ? "Eligible for paper review" : "Deployment blocked") : "No review yet"}</h2></div>
              {decision ? <em className={`ops-state ops-state--${decision.eligible ? "attention" : "danger"}`}>{decision.rules_version}</em> : null}
            </div>
            {decision ? (
              <div className="ops-risk-checks">
                {Object.entries(decision.checks).map(([check, passed]) => (
                  <div key={check} className={passed ? "is-passed" : "is-failed"}>
                    <i>{passed ? "✓" : "×"}</i>
                    <span>{check.replaceAll("_", " ")}</span>
                    <em>{passed ? "PASS" : "BLOCK"}</em>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No risk evidence" detail="Complete a study to produce an immutable risk review." />
            )}
          </article>
          <article className="ops-card">
            <div className="ops-card__heading">
              <div><span>HUMAN GATE</span><h2>Paper approval</h2></div>
            </div>
            {currentExperiment?.state === "AWAITING_HUMAN_APPROVAL" && decision?.eligible ? (
              <div className="ops-approval">
                <p>This exports a PAPER artifact only. It does not place an MT5 order.</p>
                <label>
                  Approver name
                  <input
                    value={approvalName}
                    onChange={(event) => setApprovalName(event.target.value)}
                    placeholder="Your name"
                  />
                </label>
                <button
                  disabled={!approvalName.trim() || approvalBusy}
                  onClick={() => void approvePaper()}
                >
                  {approvalBusy ? "Recording approval…" : "Approve paper export"}
                </button>
              </div>
            ) : (
              <EmptyState
                title={decision?.eligible ? "No run awaiting approval" : "Risk approval unavailable"}
                detail={
                  decision?.rejection_reasons.length
                    ? `Blocked by: ${decision.rejection_reasons.map((item) => item.replaceAll("_", " ")).join(", ")}.`
                    : "Select an eligible run that is awaiting human approval."
                }
              />
            )}
          </article>
        </div>
      </section>
    );
  }

  return (
    <section className="ops-section" data-testid="section-connections">
      <SectionHeader
        eyebrow="Connections"
        title="Installed software is not the same as a verified gateway"
        detail="Soki reports the local MT5 terminal, provider, Telegram bot, and remote bridge separately. Demo and Real account connections remain read-only."
        action={<button onClick={onManageSetup}>Manage credentials</button>}
      />
      <div className="ops-grid ops-grid--connections">
        <article className="ops-card">
          <div className="ops-card__heading">
            <div><span>LOCAL TERMINAL</span><h2>MetaTrader 5</h2></div>
            <em className={`ops-state ops-state--${inventory.localMT5?.installed ? "ready" : "danger"}`}>
              {inventory.localMT5?.installed ? "INSTALLED" : "NOT FOUND"}
            </em>
          </div>
          <div className="ops-integration-proof">
            <strong>{inventory.localMT5?.application_path || "No local application detected"}</strong>
            <p>
              The macOS application runs through Wine. Account and position data still require a
              REST or MCP bridge; the application bundle alone does not expose a safe API.
            </p>
            <dl>
              <div><dt>Platform</dt><dd>{inventory.localMT5?.platform ?? "unknown"}</dd></div>
              <div><dt>Bridge required</dt><dd>Yes</dd></div>
              <div><dt>Gateway</dt><dd>{setup.mt5.connected ? "Connected" : "Not connected"}</dd></div>
            </dl>
          </div>
        </article>
        <article className="ops-card">
          <div className="ops-card__heading">
            <div><span>MT5 SAFETY</span><h2>Account and bridge verification</h2></div>
          </div>
          <div className="ops-status-list ops-status-list--checks">
            {[
              ["Terminal installed", Boolean(inventory.localMT5?.installed), "Local application detection"],
              ["Gateway protocol", Boolean(setup.mt5.connected), String(setup.mt5.transport || "REST or MCP")],
              [
                "Account type",
                ["DEMO", "REAL"].includes(String(setup.mt5.account_mode)),
                `${String(setup.mt5.account_mode || "Unverified")} · ${
                  setup.mt5.account_mode_source === "BRIDGE_VERIFIED"
                    ? "bridge verified"
                    : "selected in setup"
                }`,
              ],
              ["Order access", Boolean(inventory.mt5?.order_access), "Must remain off in this release"],
            ].map(([label, ready, detail]) => (
              <div key={String(label)}>
                <i className={ready ? "is-ready" : ""} />
                <span><strong>{String(label)}</strong><small>{String(detail)}</small></span>
                <em>{ready ? "verified" : "required"}</em>
              </div>
            ))}
          </div>
        </article>
        <article className="ops-card">
          <div className="ops-card__heading">
            <div><span>AGENT CHANNELS</span><h2>Provider and Telegram</h2></div>
          </div>
          <div className="ops-integration-proof">
            <dl>
              <div><dt>Model</dt><dd>{setup.model.connected ? setup.model.model : "Not connected"}</dd></div>
              <div><dt>Telegram</dt><dd>{setup.telegram.inbound_ready ? String(setup.telegram.bot_username) : "Not connected"}</dd></div>
              <div><dt>Market data</dt><dd>{setup.market_data.status}</dd></div>
              <div><dt>Secret storage</dt><dd>Local 0600</dd></div>
            </dl>
            <button onClick={() => void onRefreshSetup()}>Refresh connection checks</button>
          </div>
        </article>
      </div>
      {loading ? <span className="ops-loading">Refreshing verified integration state…</span> : null}
    </section>
  );
}
