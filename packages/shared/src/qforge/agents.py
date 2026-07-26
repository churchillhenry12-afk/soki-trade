from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from qforge.model_router import ModelRouter
from qforge.schemas import (
    ConditionGroup,
    ExitRules,
    IndicatorCondition,
    ResearchObjective,
    RiskRules,
    StrategyDefinition,
)


@dataclass(frozen=True)
class AgentPolicy:
    name: str
    responsibility: str
    tools: tuple[str, ...]
    timeout_seconds: int
    retries: int
    shell_access: bool = False
    may_access_mt5_orders: bool = False
    may_override_risk: bool = False


AGENT_POLICIES = {
    "RESEARCH_DIRECTOR": AgentPolicy(
        "Research Director", "Plan typed experiments", ("experiment.create",), 30, 2
    ),
    "STRATEGY_BUILDER": AgentPolicy(
        "Strategy Builder", "Generate strategy DSL", ("strategy.validate",), 30, 2
    ),
    "BACKTESTER": AgentPolicy(
        "Backtester Agent", "Request deterministic backtests", ("backtest.run",), 300, 1
    ),
    "CRITIC": AgentPolicy("Critic Agent", "Find assumptions", ("backtest.read",), 60, 2),
    "ADVERSARY": AgentPolicy("Adversary Agent", "Propose hostile tests", ("stress.run",), 180, 1),
    "STATISTICIAN": AgentPolicy(
        "Statistician Agent", "Request robust statistics", ("statistics.run",), 300, 1
    ),
    "OPTIMIZER": AgentPolicy(
        "Optimizer Agent", "Compare classical solvers", ("optimizer.run",), 300, 1
    ),
    "QUANTUM_OPTIMIZER": AgentPolicy(
        "Quantum Optimizer Agent", "Benchmark QUBO solvers", ("quantum.run",), 300, 1
    ),
    "RISK_GOVERNOR": AgentPolicy(
        "Risk Governor", "Apply immutable risk rules", ("risk.review",), 30, 0
    ),
    "DEPLOYMENT_CONTROLLER": AgentPolicy(
        "Deployment Controller",
        "Export approved demo artifacts",
        ("deployment.export", "mt5.demo_order"),
        30,
        0,
        may_access_mt5_orders=True,
    ),
    "REPORTER": AgentPolicy("Reporter Agent", "Render evidence", ("report.render",), 60, 1),
    "MEMORY": AgentPolicy("Memory Agent", "Store decisions", ("memory.write",), 30, 2),
}


class HermesAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def verified(self) -> bool: ...

    async def plan(self, objective: ResearchObjective) -> dict[str, Any]: ...

    async def build_strategies(
        self, objective: ResearchObjective, *, seed: int
    ) -> list[StrategyDefinition]: ...


class MockHermesAdapter:
    name = "mock-hermes"
    verified = False

    async def plan(self, objective: ResearchObjective) -> dict[str, Any]:
        return {
            "hypothesis": objective.thesis,
            "symbols": objective.symbols,
            "timeframe": objective.timeframe,
            "execution": "research_only",
        }

    async def build_strategies(
        self, objective: ResearchObjective, *, seed: int
    ) -> list[StrategyDefinition]:
        del seed
        variants = ((8, 21, 14), (13, 34, 16), (21, 55, 20))
        strategies: list[StrategyDefinition] = []
        for index, (fast, slow, atr) in enumerate(variants, start=1):
            strategies.append(
                StrategyDefinition(
                    strategy_id=f"{objective.symbols[0]}-{objective.timeframe}-{index:04d}",
                    name=f"EMA {fast}/{slow} volatility gate",
                    symbols=objective.symbols,
                    timeframe=objective.timeframe,
                    entry=ConditionGroup(
                        operator="AND",
                        conditions=[
                            IndicatorCondition(
                                indicator="EMA",
                                period=fast,
                                comparison="crosses_above",
                                target_indicator="EMA",
                                target_period=slow,
                            ),
                            IndicatorCondition(
                                indicator="ATR",
                                period=atr,
                                comparison="greater_than",
                                value=0.00025,
                            ),
                        ],
                    ),
                    exit=ExitRules(
                        stop_loss_atr=1.4 + index * 0.1,
                        take_profit_atr=2.0 + index * 0.25,
                        trailing_atr=1.2,
                    ),
                    maximum_spread=0.00035,
                    risk=RiskRules(risk_per_trade=0.005),
                    allowed_direction="BOTH",
                    metadata={
                        "fast_period": fast,
                        "slow_period": slow,
                        "atr_period": atr,
                    },
                    generation_source="MOCK_HERMES",
                )
            )
        return strategies


class LocalResearchAdapter:
    """Deterministic production strategy generator that requires no model provider."""

    name = "local-deterministic-research"
    verified = True

    async def plan(self, objective: ResearchObjective) -> dict[str, Any]:
        return {
            "hypothesis": objective.thesis,
            "symbols": objective.symbols,
            "timeframe": objective.timeframe,
            "assumptions": [
                "signals are evaluated only on completed candles",
                "entries occur on the next candle",
                "spread, slippage, and commission are charged",
            ],
            "falsification": [
                "reject candidates that fail execution-cost stress tests",
                "reject candidates that breach deterministic risk limits",
            ],
            "execution": "research_and_paper_only",
            "planner": self.name,
        }

    async def build_strategies(
        self, objective: ResearchObjective, *, seed: int
    ) -> list[StrategyDefinition]:
        variants = ((8, 21, 14), (13, 34, 16), (21, 55, 20))
        strategies: list[StrategyDefinition] = []
        for index, (fast, slow, atr) in enumerate(variants, start=1):
            strategies.append(
                StrategyDefinition(
                    strategy_id=f"{objective.symbols[0]}-{objective.timeframe}-{index:04d}",
                    name=f"EMA {fast}/{slow} execution-stress candidate",
                    symbols=objective.symbols,
                    timeframe=objective.timeframe,
                    entry=ConditionGroup(
                        operator="AND",
                        conditions=[
                            IndicatorCondition(
                                indicator="EMA",
                                period=fast,
                                comparison="crosses_above",
                                target_indicator="EMA",
                                target_period=slow,
                            ),
                            IndicatorCondition(
                                indicator="ATR",
                                period=atr,
                                comparison="greater_than",
                                value=0.0,
                            ),
                        ],
                    ),
                    exit=ExitRules(
                        stop_loss_atr=1.4 + index * 0.1,
                        take_profit_atr=2.0 + index * 0.25,
                        trailing_atr=1.2,
                    ),
                    maximum_spread=0.00035,
                    risk=RiskRules(risk_per_trade=0.005),
                    allowed_direction="BOTH",
                    metadata={
                        "fast_period": fast,
                        "slow_period": slow,
                        "atr_period": atr,
                        "seed": seed,
                        "engine": self.name,
                    },
                    generation_source="LOCAL_ENGINE",
                )
            )
        return strategies


class ModelHermesAdapter:
    name = "model-router-hermes"

    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    @property
    def verified(self) -> bool:
        status = self.router.status()
        return bool(status["configured"]) and status["provider"] != "mock"

    async def plan(self, objective: ResearchObjective) -> dict[str, Any]:
        self._require_real_provider()
        response = await self.router.complete(
            (
                "Create a research-only experiment plan for this objective. Return one JSON "
                "object with keys hypothesis, symbols, timeframe, assumptions, falsification, "
                f"and execution. Objective:\n{objective.model_dump_json()}"
            ),
            system_prompt=(
                "You are the Soki Trade Research Director. Return strict JSON only. "
                "Design falsifiable trading research; never place or suggest live orders."
            ),
        )
        payload = _parse_json(response)
        if not isinstance(payload, dict):
            raise ValueError("research director returned a non-object plan")
        return {str(key): value for key, value in payload.items()}

    async def build_strategies(
        self, objective: ResearchObjective, *, seed: int
    ) -> list[StrategyDefinition]:
        self._require_real_provider()
        response = await self.router.complete(
            (
                "Generate 3 distinct strategy definitions for the objective below. Return a "
                'JSON object shaped as {"strategies": [...]}. Every strategy must use this '
                "schema: strategy_id (uppercase letters/numbers/hyphens), name, symbols, "
                "timeframe, entry={operator:'AND'|'OR',conditions:[{indicator:'EMA'|'ATR'|'RSI',"
                "period:2..250,comparison:'crosses_above'|'crosses_below'|'greater_than'|"
                "'less_than',target_indicator,target_period,value}]}, "
                "exit={stop_loss_atr,take_profit_atr,trailing_atr}, filters, trading_sessions, "
                "maximum_spread, risk={risk_per_trade<=0.005,maximum_concurrent_positions}, "
                "allowed_direction, metadata, parent_strategy. For cross comparisons include "
                "target_indicator and target_period; for numeric comparisons include value. "
                f"Reproducibility seed={seed}. Objective:\n{objective.model_dump_json()}"
            ),
            system_prompt=(
                "You are the Soki Trade Strategy Builder. Return strict JSON only. "
                "Produce typed research strategies, never executable broker code."
            ),
        )
        payload = _parse_json(response)
        raw_strategies = payload.get("strategies") if isinstance(payload, dict) else payload
        if not isinstance(raw_strategies, list) or not raw_strategies:
            raise ValueError("strategy builder returned no strategies")
        strategies: list[StrategyDefinition] = []
        for raw_strategy in raw_strategies[:8]:
            if not isinstance(raw_strategy, dict):
                raise ValueError("strategy builder returned a non-object strategy")
            normalized = {
                **raw_strategy,
                "symbols": objective.symbols,
                "timeframe": objective.timeframe,
                "generation_source": "HERMES",
            }
            strategies.append(StrategyDefinition.model_validate(normalized))
        return strategies

    def _require_real_provider(self) -> None:
        if not self.verified:
            raise ValueError(
                "production research requires a configured non-mock model provider; "
                "open terminal SETUP API with F2"
            )


class ProductionHermesAdapter:
    """Reliable production research; the model router independently powers chat."""

    def __init__(self, router: ModelRouter) -> None:
        self.local = LocalResearchAdapter()
        self.model = ModelHermesAdapter(router)

    @property
    def name(self) -> str:
        return self.local.name

    @property
    def verified(self) -> bool:
        return True

    @property
    def model_configured(self) -> bool:
        return self.model.verified

    async def plan(self, objective: ResearchObjective) -> dict[str, Any]:
        return await self.local.plan(objective)

    async def build_strategies(
        self, objective: ResearchObjective, *, seed: int
    ) -> list[StrategyDefinition]:
        return await self.local.build_strategies(objective, seed=seed)


def _parse_json(response: str) -> Any:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    object_start = cleaned.find("{")
    array_start = cleaned.find("[")
    starts = [index for index in (object_start, array_start) if index >= 0]
    if not starts:
        raise ValueError("model response did not contain JSON")
    start = min(starts)
    closing = "}" if cleaned[start] == "{" else "]"
    end = cleaned.rfind(closing)
    if end < start:
        raise ValueError("model response contained incomplete JSON")
    return json.loads(cleaned[start : end + 1])
