from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Mode(StrEnum):
    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    MT5_DEMO = "MT5_DEMO"
    LIVE_DISABLED = "LIVE_DISABLED"


class AttachmentKind(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    ARCHIVE = "ARCHIVE"
    OTHER = "OTHER"


class Attachment(BaseModel):
    attachment_id: UUID = Field(default_factory=uuid4)
    owner: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=160)
    kind: AttachmentKind
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage_path: str = Field(min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)


class ExperimentState(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    BACKTESTING = "BACKTESTING"
    CRITICIZING = "CRITICIZING"
    ADVERSARIAL_TESTING = "ADVERSARIAL_TESTING"
    STATISTICAL_VALIDATION = "STATISTICAL_VALIDATION"
    OPTIMIZING = "OPTIMIZING"
    QUANTUM_OPTIMIZING = "QUANTUM_OPTIMIZING"
    RISK_REVIEW = "RISK_REVIEW"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    APPROVED_FOR_PAPER = "APPROVED_FOR_PAPER"
    APPROVED_FOR_DEMO = "APPROVED_FOR_DEMO"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResearchObjectiveCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    thesis: str = Field(min_length=12, max_length=2_000)
    symbols: list[str] = Field(default_factory=lambda: ["EURUSD"], min_length=1, max_length=8)
    timeframe: Literal["M5", "M15", "M30", "H1", "H4", "D1"] = "M15"

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        cleaned = [symbol.strip().upper() for symbol in symbols]
        if any(not symbol.isalnum() for symbol in cleaned):
            raise ValueError("symbols must be alphanumeric")
        return cleaned


class ResearchObjective(ResearchObjectiveCreate):
    objective_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)


class IndicatorCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator: Literal["EMA", "ATR", "RSI"]
    period: int = Field(ge=2, le=250)
    comparison: Literal[
        "crosses_above",
        "crosses_below",
        "greater_than",
        "less_than",
    ]
    target_indicator: Literal["EMA", "ATR", "RSI"] | None = None
    target_period: int | None = Field(default=None, ge=2, le=250)
    value: float | None = None

    @model_validator(mode="after")
    def validate_target(self) -> IndicatorCondition:
        crosses = self.comparison.startswith("crosses_")
        if crosses and (self.target_indicator is None or self.target_period is None):
            raise ValueError("cross comparisons require a target indicator and period")
        if not crosses and self.value is None:
            raise ValueError("numeric comparisons require a value")
        return self


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: Literal["AND", "OR"] = "AND"
    conditions: list[IndicatorCondition] = Field(min_length=1, max_length=8)


class ExitRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_loss_atr: float = Field(gt=0.1, le=10)
    take_profit_atr: float = Field(gt=0.1, le=20)
    trailing_atr: float | None = Field(default=None, gt=0.1, le=10)


class RiskRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_per_trade: float = Field(gt=0, le=0.005)
    maximum_concurrent_positions: int = Field(default=1, ge=1, le=10)


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = Field(pattern=r"^[A-Z0-9-]{4,64}$")
    name: str = Field(min_length=3, max_length=100)
    version: int = Field(default=1, ge=1)
    symbols: list[str] = Field(min_length=1, max_length=8)
    timeframe: Literal["M5", "M15", "M30", "H1", "H4", "D1"]
    entry: ConditionGroup
    exit: ExitRules
    filters: list[IndicatorCondition] = Field(default_factory=list, max_length=8)
    trading_sessions: list[str] = Field(default_factory=lambda: ["00:00-23:59"])
    maximum_spread: float = Field(default=0.0003, ge=0, le=0.01)
    risk: RiskRules
    allowed_direction: Literal["LONG", "SHORT", "BOTH"] = "BOTH"
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    parent_strategy: str | None = None
    generation_source: Literal["MOCK_HERMES", "LOCAL_ENGINE", "HERMES", "HUMAN"]


class ExperimentCreate(BaseModel):
    objective_id: UUID
    parent_experiment_id: UUID | None = None
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


class Experiment(BaseModel):
    experiment_id: UUID = Field(default_factory=uuid4)
    objective_id: UUID
    correlation_id: UUID = Field(default_factory=uuid4)
    parent_experiment_id: UUID | None = None
    state: ExperimentState = ExperimentState.CREATED
    status: RunStatus = RunStatus.PENDING
    seed: int = 42
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    report: FinalReport | None = None


class ExperimentEvent(BaseModel):
    sequence: int = Field(ge=1)
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    experiment_id: UUID
    correlation_id: UUID
    actor: str = "system"
    agent: str
    event_type: str
    state: ExperimentState
    status: RunStatus
    payload: dict[str, Any] = Field(default_factory=dict)


class Trade(BaseModel):
    direction: Literal["LONG", "SHORT"]
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    bars_held: int
    exit_reason: Literal["STOP", "TARGET", "TRAIL", "SIGNAL", "END"]


class BacktestMetrics(BaseModel):
    net_return: float
    annualized_return: float
    maximum_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float
    expectancy: float
    win_rate: float
    average_win: float
    average_loss: float
    consecutive_losses: int
    exposure: float
    turnover: float
    number_of_trades: int
    time_in_market: float
    recovery_factor: float
    monthly_return_distribution: dict[str, float]
    regime_performance: dict[str, float]


class BacktestResult(BaseModel):
    backtest_id: UUID = Field(default_factory=uuid4)
    strategy_id: str
    seed: int
    started_at: datetime
    completed_at: datetime
    assumptions: dict[str, float | str]
    metrics: BacktestMetrics
    trades: list[Trade]
    equity_curve: list[float]


class Critique(BaseModel):
    strategy_id: str
    weaknesses: list[str]
    severity: Literal["LOW", "MEDIUM", "HIGH"]


class AdversarialResult(BaseModel):
    strategy_id: str
    spread_multiplier: float
    slippage_multiplier: float
    stressed_return: float
    degradation: float
    passed: bool


class StatisticalResult(BaseModel):
    strategy_id: str
    robustness_score: float = Field(ge=0, le=1)
    overfitting_risk: float = Field(ge=0, le=1)
    execution_realism_score: float = Field(ge=0, le=1)
    regime_stability_score: float = Field(ge=0, le=1)
    deployment_recommendation: Literal["REJECT", "RESEARCH", "PAPER"]
    rejection_reasons: list[str]


class SolverResult(BaseModel):
    solver: str
    solution: list[str]
    objective_score: float
    runtime_ms: float
    iterations: int
    constraint_violations: list[str]
    seed: int
    verified: bool


class SolverBenchmark(BaseModel):
    problem: str
    solvers: dict[str, SolverResult]
    winner: str
    validation_required: bool = True


class RiskDecision(BaseModel):
    eligible: bool
    approved: bool
    target_mode: Mode
    checks: dict[str, bool]
    rejection_reasons: list[str]
    rules_version: str


class ApprovalCreate(BaseModel):
    experiment_id: UUID
    approver: str = Field(min_length=2, max_length=120)
    target_mode: Literal[Mode.PAPER, Mode.MT5_DEMO] = Mode.PAPER
    acknowledged_no_live_trading: Literal[True]


class Approval(BaseModel):
    approval_id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    approver: str
    target_mode: Mode
    created_at: datetime = Field(default_factory=utc_now)


class FinalReport(BaseModel):
    experiment_id: UUID
    objective: ResearchObjective
    strategies: list[StrategyDefinition]
    backtests: list[BacktestResult]
    critiques: list[Critique]
    adversarial_results: list[AdversarialResult]
    statistical_results: list[StatisticalResult]
    classical_selection: SolverResult
    solver_benchmark: SolverBenchmark
    risk_decision: RiskDecision
    generated_at: datetime = Field(default_factory=utc_now)


Experiment.model_rebuild()


class ProofCheckStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class AgentTaskStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class ProofCheck(BaseModel):
    key: str
    label: str
    status: ProofCheckStatus = ProofCheckStatus.PENDING
    evidence: str = ""


class TaskCheckpoint(BaseModel):
    checkpoint_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    label: str
    status: AgentTaskStatus


class AgentTask(BaseModel):
    task_id: UUID = Field(default_factory=uuid4)
    session_id: str
    request: str
    status: AgentTaskStatus = AgentTaskStatus.RUNNING
    runtime: str = "soki-core"
    checks: list[ProofCheck]
    checkpoints: list[TaskCheckpoint] = Field(default_factory=list)
    experiment_id: UUID | None = None
    response: str = ""
    error: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SystemStatus(BaseModel):
    version: str
    mode: Mode
    runtime: Literal["PRODUCTION", "DEMO"]
    hermes: dict[str, str | bool]
    market_data: dict[str, str | bool]
    mt5: dict[str, str | bool]
    quantum: dict[str, str | bool]
    uptime_seconds: float
