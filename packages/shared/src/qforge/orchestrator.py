from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from typing import Any
from uuid import UUID

import structlog

from qforge.agents import HermesAdapter
from qforge.analysis import criticize, run_adversarial_tests, score_robustness
from qforge.backtester import run_backtest
from qforge.database import (
    AdversarialTests,
    Backtests,
    OptimizationRuns,
    QuantumJobs,
    Repository,
    RiskReviews,
    SolverBenchmarks,
    StatisticalTests,
    Strategies,
)
from qforge.market_data import MarketDataAdapter
from qforge.optimizer import select_portfolio
from qforge.quantum import QuantumBackend, benchmark
from qforge.risk import review_risk
from qforge.schemas import (
    Approval,
    Experiment,
    ExperimentCreate,
    ExperimentEvent,
    ExperimentState,
    FinalReport,
    Mode,
    ResearchObjective,
    ResearchObjectiveCreate,
    RunStatus,
)
from qforge.state_machine import ensure_transition

logger = structlog.get_logger()


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[UUID | None, set[asyncio.Queue[ExperimentEvent]]] = defaultdict(set)

    async def publish(self, event: ExperimentEvent) -> None:
        queues = self._subscribers[None] | self._subscribers[event.experiment_id]
        for queue in queues:
            await queue.put(event)

    def subscribe(self, experiment_id: UUID | None = None) -> asyncio.Queue[ExperimentEvent]:
        queue: asyncio.Queue[ExperimentEvent] = asyncio.Queue(maxsize=500)
        self._subscribers[experiment_id].add(queue)
        return queue

    def unsubscribe(
        self, queue: asyncio.Queue[ExperimentEvent], experiment_id: UUID | None = None
    ) -> None:
        self._subscribers[experiment_id].discard(queue)


class ExperimentOrchestrator:
    def __init__(
        self,
        repository: Repository,
        hermes: HermesAdapter,
        market_data: MarketDataAdapter,
        quantum: QuantumBackend,
    ) -> None:
        self.repository = repository
        self.hermes = hermes
        self.market_data = market_data
        self.quantum = quantum
        self.events = EventBus()
        self.tasks: dict[UUID, asyncio.Task[None]] = {}
        self.pause_requested: set[UUID] = set()
        self.cancel_requested: set[UUID] = set()
        self.resume_state: dict[UUID, ExperimentState] = {}

    def create_objective(self, request: ResearchObjectiveCreate) -> ResearchObjective:
        return self.repository.add_objective(ResearchObjective(**request.model_dump()))

    def create_experiment(self, request: ExperimentCreate) -> Experiment:
        if self.repository.get_objective(request.objective_id) is None:
            raise KeyError(str(request.objective_id))
        return self.repository.add_experiment(Experiment(**request.model_dump()))

    async def _emit(
        self,
        experiment: Experiment,
        agent: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> ExperimentEvent:
        event = ExperimentEvent(
            sequence=len(self.repository.events(experiment.experiment_id)) + 1,
            experiment_id=experiment.experiment_id,
            correlation_id=experiment.correlation_id,
            agent=agent,
            event_type=event_type,
            state=experiment.state,
            status=experiment.status,
            payload=payload or {},
        )
        self.repository.add_event(event)
        await self.events.publish(event)
        logger.info(
            event_type,
            experiment_id=str(experiment.experiment_id),
            correlation_id=str(experiment.correlation_id),
            agent=agent,
            state=experiment.state,
            payload=payload or {},
        )
        return event

    async def _transition(
        self,
        experiment: Experiment,
        target: ExperimentState,
        agent: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        ensure_transition(experiment.state, target)
        experiment.state = target
        experiment.status = (
            RunStatus.CANCELLED
            if target == ExperimentState.CANCELLED
            else RunStatus.FAILED
            if target == ExperimentState.FAILED
            else RunStatus.RUNNING
        )
        self.repository.save_experiment(experiment)
        await self._emit(experiment, agent, event_type, payload)

    async def _checkpoint(self, experiment: Experiment, next_state: ExperimentState) -> None:
        if experiment.experiment_id in self.cancel_requested:
            await self._transition(
                experiment,
                ExperimentState.CANCELLED,
                "SYSTEM",
                "experiment.cancelled",
            )
            raise asyncio.CancelledError
        if experiment.experiment_id in self.pause_requested:
            self.resume_state[experiment.experiment_id] = next_state
            await self._transition(
                experiment,
                ExperimentState.PAUSED,
                "SYSTEM",
                "experiment.paused",
            )
            while experiment.experiment_id in self.pause_requested:
                if experiment.experiment_id in self.cancel_requested:
                    await self._transition(
                        experiment,
                        ExperimentState.CANCELLED,
                        "SYSTEM",
                        "experiment.cancelled",
                    )
                    raise asyncio.CancelledError
                await asyncio.sleep(0.05)
            await self._transition(
                experiment,
                next_state,
                "SYSTEM",
                "experiment.resumed",
            )

    def start(self, experiment_id: UUID) -> Experiment:
        experiment = self.repository.get_experiment(experiment_id)
        if experiment is None:
            raise KeyError(str(experiment_id))
        existing = self.tasks.get(experiment_id)
        if existing and not existing.done():
            raise ValueError("experiment is already running")
        if experiment.state != ExperimentState.CREATED:
            raise ValueError(f"experiment cannot start from {experiment.state}")
        self.tasks[experiment_id] = asyncio.create_task(self._run(experiment_id))
        return experiment

    def pause(self, experiment_id: UUID) -> Experiment:
        experiment = self._require_active(experiment_id)
        self.pause_requested.add(experiment_id)
        return experiment

    def resume(self, experiment_id: UUID) -> Experiment:
        experiment = self.repository.get_experiment(experiment_id)
        if experiment is None:
            raise KeyError(str(experiment_id))
        self.pause_requested.discard(experiment_id)
        return experiment

    def cancel(self, experiment_id: UUID) -> Experiment:
        experiment = self._require_active(experiment_id)
        self.cancel_requested.add(experiment_id)
        return experiment

    def _require_active(self, experiment_id: UUID) -> Experiment:
        experiment = self.repository.get_experiment(experiment_id)
        task = self.tasks.get(experiment_id)
        if experiment is None:
            raise KeyError(str(experiment_id))
        if task is None or task.done():
            raise ValueError("experiment is not active")
        return experiment

    async def approve(self, approval: Approval) -> Experiment:
        experiment = self.repository.get_experiment(approval.experiment_id)
        if experiment is None:
            raise KeyError(str(approval.experiment_id))
        if experiment.state != ExperimentState.AWAITING_HUMAN_APPROVAL or experiment.report is None:
            raise ValueError("experiment is not awaiting approval")
        decision = review_risk(
            experiment.report.backtests,
            experiment.report.statistical_results,
            experiment.report.classical_selection,
            human_approved=True,
            target_mode=approval.target_mode,
            demo_account_verified=False,
        )
        experiment.report.risk_decision = decision
        if not decision.approved:
            self.repository.save_experiment(experiment)
            await self._emit(
                experiment,
                "RISK_GOVERNOR",
                "approval.blocked",
                {"reasons": decision.rejection_reasons},
            )
            return experiment
        target = (
            ExperimentState.APPROVED_FOR_PAPER
            if approval.target_mode == Mode.PAPER
            else ExperimentState.APPROVED_FOR_DEMO
        )
        await self._transition(
            experiment,
            target,
            "DEPLOYMENT_CONTROLLER",
            "deployment.export_approved",
            {"mode": approval.target_mode, "orders_placed": 0},
        )
        await self._transition(
            experiment,
            ExperimentState.COMPLETED,
            "REPORTER",
            "experiment.completed",
            {"orders_placed": 0},
        )
        experiment.status = RunStatus.SUCCEEDED
        self.repository.save_experiment(experiment)
        return experiment

    async def _run(self, experiment_id: UUID) -> None:
        experiment = self.repository.get_experiment(experiment_id)
        if experiment is None:
            return
        objective = self.repository.get_objective(experiment.objective_id)
        if objective is None:
            return
        try:
            await self._transition(
                experiment,
                ExperimentState.PLANNING,
                "RESEARCH_DIRECTOR",
                "objective.planning_started",
            )
            plan = await self.hermes.plan(objective)
            await self._emit(experiment, "RESEARCH_DIRECTOR", "objective.planned", plan)
            await self._checkpoint(experiment, ExperimentState.GENERATING)
            await self._transition(
                experiment,
                ExperimentState.GENERATING,
                "STRATEGY_BUILDER",
                "strategy.batch_started",
            )
            strategies = await self.hermes.build_strategies(objective, seed=experiment.seed)
            for strategy in strategies:
                self.repository.save_resource(
                    Strategies,
                    experiment_id=experiment.experiment_id,
                    correlation_id=experiment.correlation_id,
                    agent="STRATEGY_BUILDER",
                    status="VALIDATED",
                    payload=strategy.model_dump(mode="json"),
                )
                await self._emit(
                    experiment,
                    "STRATEGY_BUILDER",
                    "strategy.generated",
                    {"strategy_id": strategy.strategy_id},
                )
            await self._checkpoint(experiment, ExperimentState.BACKTESTING)
            await self._transition(
                experiment,
                ExperimentState.BACKTESTING,
                "BACKTESTER",
                "backtest.batch_started",
                {"jobs": len(strategies)},
            )
            bars = await asyncio.to_thread(
                self.market_data.bars,
                objective.symbols[0],
                objective.timeframe,
                seed=experiment.seed,
            )
            backtests = []
            for strategy in strategies:
                result = await asyncio.to_thread(run_backtest, strategy, bars, seed=experiment.seed)
                backtests.append(result)
                self.repository.save_resource(
                    Backtests,
                    experiment_id=experiment.experiment_id,
                    correlation_id=experiment.correlation_id,
                    agent="BACKTESTER",
                    status="COMPLETED",
                    payload=result.model_dump(mode="json"),
                )
                await self._emit(
                    experiment,
                    "BACKTESTER",
                    "backtest.completed",
                    {
                        "strategy_id": strategy.strategy_id,
                        "net_return": result.metrics.net_return,
                        "trades": result.metrics.number_of_trades,
                    },
                )
            await self._checkpoint(experiment, ExperimentState.CRITICIZING)
            await self._transition(
                experiment,
                ExperimentState.CRITICIZING,
                "CRITIC",
                "critique.started",
            )
            critiques = [criticize(result) for result in backtests]
            for critique in critiques:
                await self._emit(
                    experiment,
                    "CRITIC",
                    "weakness.detected" if critique.weaknesses else "strategy.accepted",
                    critique.model_dump(mode="json"),
                )
            await self._checkpoint(experiment, ExperimentState.ADVERSARIAL_TESTING)
            await self._transition(
                experiment,
                ExperimentState.ADVERSARIAL_TESTING,
                "ADVERSARY",
                "stress_test.batch_started",
            )
            adversarial = []
            for strategy, backtest in zip(strategies, backtests, strict=True):
                attacks = await asyncio.to_thread(
                    run_adversarial_tests,
                    strategy,
                    backtest,
                    bars,
                    seed=experiment.seed,
                )
                adversarial.extend(attacks)
                for attack in attacks:
                    self.repository.save_resource(
                        AdversarialTests,
                        experiment_id=experiment.experiment_id,
                        correlation_id=experiment.correlation_id,
                        agent="ADVERSARY",
                        status="PASSED" if attack.passed else "FAILED",
                        payload=attack.model_dump(mode="json"),
                    )
                    await self._emit(
                        experiment,
                        "ADVERSARY",
                        "stress_test.completed",
                        attack.model_dump(mode="json"),
                    )
            await self._checkpoint(experiment, ExperimentState.STATISTICAL_VALIDATION)
            await self._transition(
                experiment,
                ExperimentState.STATISTICAL_VALIDATION,
                "STATISTICIAN",
                "statistics.started",
            )
            statistics = []
            for backtest, critique in zip(backtests, critiques, strict=True):
                attacks = [
                    attack for attack in adversarial if attack.strategy_id == backtest.strategy_id
                ]
                statistical_result = score_robustness(backtest, critique, attacks)
                statistics.append(statistical_result)
                self.repository.save_resource(
                    StatisticalTests,
                    experiment_id=experiment.experiment_id,
                    correlation_id=experiment.correlation_id,
                    agent="STATISTICIAN",
                    status="COMPLETED",
                    payload=statistical_result.model_dump(mode="json"),
                )
                await self._emit(
                    experiment,
                    "STATISTICIAN",
                    "robustness.scored",
                    statistical_result.model_dump(mode="json"),
                )
            await self._checkpoint(experiment, ExperimentState.OPTIMIZING)
            await self._transition(
                experiment,
                ExperimentState.OPTIMIZING,
                "OPTIMIZER",
                "optimizer.started",
            )
            classical = select_portfolio(statistics, seed=experiment.seed)
            self.repository.save_resource(
                OptimizationRuns,
                experiment_id=experiment.experiment_id,
                correlation_id=experiment.correlation_id,
                agent="OPTIMIZER",
                status="COMPLETED",
                payload=classical.model_dump(mode="json"),
            )
            await self._emit(
                experiment, "OPTIMIZER", "portfolio.selected", classical.model_dump(mode="json")
            )
            await self._checkpoint(experiment, ExperimentState.QUANTUM_OPTIMIZING)
            await self._transition(
                experiment,
                ExperimentState.QUANTUM_OPTIMIZING,
                "QUANTUM_OPTIMIZER",
                "qubo.compiled",
                {"variables": len(statistics), "backend": self.quantum.name},
            )
            quantum_result = self.quantum.solve(statistics, seed=experiment.seed)
            solver_benchmark = benchmark(classical, quantum_result)
            self.repository.save_resource(
                QuantumJobs,
                experiment_id=experiment.experiment_id,
                correlation_id=experiment.correlation_id,
                agent="QUANTUM_OPTIMIZER",
                status="COMPLETED" if self.quantum.verified else "MOCK_COMPLETED",
                payload=quantum_result.model_dump(mode="json"),
            )
            self.repository.save_resource(
                SolverBenchmarks,
                experiment_id=experiment.experiment_id,
                correlation_id=experiment.correlation_id,
                agent="QUANTUM_OPTIMIZER",
                status="COMPLETED",
                payload=solver_benchmark.model_dump(mode="json"),
            )
            await self._emit(
                experiment,
                "QUANTUM_OPTIMIZER",
                "benchmark.completed",
                {
                    "winner": solver_benchmark.winner,
                    "quantum_verified": quantum_result.verified,
                },
            )
            await self._checkpoint(experiment, ExperimentState.RISK_REVIEW)
            await self._transition(
                experiment,
                ExperimentState.RISK_REVIEW,
                "RISK_GOVERNOR",
                "risk.review_started",
            )
            risk = review_risk(backtests, statistics, classical)
            report = FinalReport(
                experiment_id=experiment.experiment_id,
                objective=objective,
                strategies=strategies,
                backtests=backtests,
                critiques=critiques,
                adversarial_results=adversarial,
                statistical_results=statistics,
                classical_selection=classical,
                solver_benchmark=solver_benchmark,
                risk_decision=risk,
            )
            experiment.report = report
            self.repository.save_resource(
                RiskReviews,
                experiment_id=experiment.experiment_id,
                correlation_id=experiment.correlation_id,
                agent="RISK_GOVERNOR",
                status="ELIGIBLE" if risk.eligible else "REJECTED",
                payload=risk.model_dump(mode="json"),
            )
            if risk.eligible:
                await self._transition(
                    experiment,
                    ExperimentState.AWAITING_HUMAN_APPROVAL,
                    "RISK_GOVERNOR",
                    "risk.human_approval_required",
                    risk.model_dump(mode="json"),
                )
            else:
                await self._transition(
                    experiment,
                    ExperimentState.REJECTED,
                    "RISK_GOVERNOR",
                    "risk.deployment_rejected",
                    risk.model_dump(mode="json"),
                )
            experiment.status = RunStatus.SUCCEEDED
            self.repository.save_experiment(experiment)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception(
                "experiment.failed", error=str(error), experiment_id=str(experiment_id)
            )
            latest = self.repository.get_experiment(experiment_id)
            if latest is not None and latest.state not in {
                ExperimentState.CANCELLED,
                ExperimentState.FAILED,
            }:
                with suppress(Exception):
                    await self._transition(
                        latest,
                        ExperimentState.FAILED,
                        "SYSTEM",
                        "experiment.failed",
                        {"error": type(error).__name__, "detail": str(error)},
                    )
