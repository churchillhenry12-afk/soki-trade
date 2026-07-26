from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from qforge.schemas import (
    Experiment,
    ExperimentEvent,
    ExperimentState,
    FinalReport,
    ResearchObjective,
    RunStatus,
    utc_now,
)


class Base(DeclarativeBase):
    pass


class ObjectiveRow(Base):
    __tablename__ = "research_objectives"

    objective_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ExperimentRow(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    objective_id: Mapped[str] = mapped_column(String(36), index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ExperimentEventRow(Base):
    __tablename__ = "experiment_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    experiment_id: Mapped[str] = mapped_column(String(36), index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(80))
    agent: Mapped[str] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditEntity:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    agent: Mapped[str] = mapped_column(String(80), default="none")
    correlation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(30), default="CREATED")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def _audit_model(class_name: str, table_name: str) -> type[Base]:
    return type(class_name, (AuditEntity, Base), {"__tablename__": table_name})


Users = _audit_model("Users", "users")
Projects = _audit_model("Projects", "projects")
AgentRuns = _audit_model("AgentRuns", "agent_runs")
AgentMessages = _audit_model("AgentMessages", "agent_messages")
Strategies = _audit_model("Strategies", "strategies")
StrategyVersions = _audit_model("StrategyVersions", "strategy_versions")
Backtests = _audit_model("Backtests", "backtests")
Trades = _audit_model("Trades", "trades")
Metrics = _audit_model("Metrics", "metrics")
AdversarialTests = _audit_model("AdversarialTests", "adversarial_tests")
StatisticalTests = _audit_model("StatisticalTests", "statistical_tests")
OptimizationRuns = _audit_model("OptimizationRuns", "optimization_runs")
QuantumJobs = _audit_model("QuantumJobs", "quantum_jobs")
SolverBenchmarks = _audit_model("SolverBenchmarks", "solver_benchmarks")
RiskReviews = _audit_model("RiskReviews", "risk_reviews")
Approvals = _audit_model("Approvals", "approvals")
Deployments = _audit_model("Deployments", "deployments")
MT5Accounts = _audit_model("MT5Accounts", "mt5_accounts")
AuditLogs = _audit_model("AuditLogs", "audit_logs")
SystemSettings = _audit_model("SystemSettings", "system_settings")


class Repository:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite:///"):
            path = Path(database_url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(database_url)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def add_objective(self, objective: ResearchObjective) -> ResearchObjective:
        with self.session_factory() as session:
            session.add(
                ObjectiveRow(
                    objective_id=str(objective.objective_id),
                    created_at=objective.created_at,
                    payload=objective.model_dump(mode="json"),
                )
            )
            session.commit()
        return objective

    def list_objectives(self) -> list[ResearchObjective]:
        with self.session_factory() as session:
            rows = session.query(ObjectiveRow).order_by(ObjectiveRow.created_at.desc()).all()
            return [ResearchObjective.model_validate(row.payload) for row in rows]

    def get_objective(self, objective_id: UUID) -> ResearchObjective | None:
        with self.session_factory() as session:
            row = session.get(ObjectiveRow, str(objective_id))
            return ResearchObjective.model_validate(row.payload) if row else None

    def add_experiment(self, experiment: Experiment) -> Experiment:
        with self.session_factory() as session:
            session.add(self._experiment_row(experiment))
            session.commit()
        return experiment

    @staticmethod
    def _experiment_row(experiment: Experiment) -> ExperimentRow:
        return ExperimentRow(
            experiment_id=str(experiment.experiment_id),
            objective_id=str(experiment.objective_id),
            correlation_id=str(experiment.correlation_id),
            state=experiment.state,
            status=experiment.status,
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
            payload=experiment.model_dump(mode="json"),
        )

    def save_experiment(self, experiment: Experiment) -> Experiment:
        experiment.updated_at = utc_now()
        with self.session_factory() as session:
            row = session.get(ExperimentRow, str(experiment.experiment_id))
            if row is None:
                session.add(self._experiment_row(experiment))
            else:
                row.state = experiment.state
                row.status = experiment.status
                row.updated_at = experiment.updated_at
                row.payload = experiment.model_dump(mode="json")
            session.commit()
        return experiment

    def get_experiment(self, experiment_id: UUID) -> Experiment | None:
        with self.session_factory() as session:
            row = session.get(ExperimentRow, str(experiment_id))
            return Experiment.model_validate(row.payload) if row else None

    def list_experiments(self) -> list[Experiment]:
        with self.session_factory() as session:
            rows = session.query(ExperimentRow).order_by(ExperimentRow.created_at.desc()).all()
            return [Experiment.model_validate(row.payload) for row in rows]

    def add_event(self, event: ExperimentEvent) -> ExperimentEvent:
        with self.session_factory() as session:
            session.add(
                ExperimentEventRow(
                    event_id=str(event.event_id),
                    sequence=event.sequence,
                    timestamp=event.timestamp,
                    experiment_id=str(event.experiment_id),
                    correlation_id=str(event.correlation_id),
                    actor=event.actor,
                    agent=event.agent,
                    event_type=event.event_type,
                    state=event.state,
                    status=event.status,
                    payload=event.payload,
                )
            )
            session.commit()
        return event

    def events(self, experiment_id: UUID, *, after: int = 0) -> list[ExperimentEvent]:
        with self.session_factory() as session:
            rows = (
                session.query(ExperimentEventRow)
                .filter(
                    ExperimentEventRow.experiment_id == str(experiment_id),
                    ExperimentEventRow.sequence > after,
                )
                .order_by(ExperimentEventRow.sequence)
                .all()
            )
            return [
                ExperimentEvent(
                    sequence=row.sequence,
                    event_id=UUID(row.event_id),
                    timestamp=row.timestamp,
                    experiment_id=UUID(row.experiment_id),
                    correlation_id=UUID(row.correlation_id),
                    actor=row.actor,
                    agent=row.agent,
                    event_type=row.event_type,
                    state=ExperimentState(row.state),
                    status=RunStatus(row.status),
                    payload=row.payload,
                )
                for row in rows
            ]

    def save_resource(
        self,
        model: type[Any],
        *,
        experiment_id: UUID,
        correlation_id: UUID,
        agent: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        with self.session_factory() as session:
            session.add(
                model(
                    experiment_id=str(experiment_id),
                    correlation_id=str(correlation_id),
                    agent=agent,
                    status=status,
                    payload=payload,
                )
            )
            session.commit()

    def strategies(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = cast(list[Any], session.query(Strategies).all())
            return [cast(dict[str, Any], row.payload) for row in rows]

    def backtests(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = cast(list[Any], session.query(Backtests).all())
            return [cast(dict[str, Any], row.payload) for row in rows]

    def risk_reviews(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = cast(list[Any], session.query(RiskReviews).all())
            return [cast(dict[str, Any], row.payload) for row in rows]

    def set_report(self, experiment_id: UUID, report: FinalReport) -> Experiment:
        experiment = self.get_experiment(experiment_id)
        if experiment is None:
            raise KeyError(str(experiment_id))
        experiment.report = report
        return self.save_experiment(experiment)
