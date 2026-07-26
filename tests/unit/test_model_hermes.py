from typing import Any, cast

from qforge.agents import LocalResearchAdapter, ModelHermesAdapter, ProductionHermesAdapter
from qforge.model_router import ModelRouter
from qforge.schemas import ResearchObjective


class StubRouter:
    def __init__(self) -> None:
        self.responses = [
            '{"hypothesis":"cost-aware edge","symbols":["EURUSD"],'
            '"timeframe":"M15","assumptions":[],"falsification":"negative OOS",'
            '"execution":"research_only"}',
            """
            {"strategies":[{
              "strategy_id":"EURUSD-M15-REAL-01",
              "name":"Model generated crossover",
              "entry":{"operator":"AND","conditions":[{
                "indicator":"EMA","period":10,"comparison":"crosses_above",
                "target_indicator":"EMA","target_period":30
              }]},
              "exit":{"stop_loss_atr":1.5,"take_profit_atr":2.5,"trailing_atr":1.2},
              "filters":[],"trading_sessions":["07:00-17:00"],
              "maximum_spread":0.0003,
              "risk":{"risk_per_trade":0.005,"maximum_concurrent_positions":1},
              "allowed_direction":"BOTH","metadata":{"seed":42},"parent_strategy":null
            }]}
            """,
        ]

    def status(self) -> dict[str, str | bool]:
        return {
            "configured": True,
            "provider": "openai_compatible",
            "model": "real-model",
            "base_url": "https://provider.example/v1",
            "api_key_present": True,
            "secret_storage": "LOCAL_0600",
        }

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        assert prompt
        assert system_prompt
        return self.responses.pop(0)


async def test_model_hermes_builds_typed_non_mock_research() -> None:
    router = cast(ModelRouter, cast(Any, StubRouter()))
    adapter = ModelHermesAdapter(router)
    objective = ResearchObjective(
        title="Real provider research",
        thesis="Test a real model-generated hypothesis on supplied historical bars.",
        symbols=["EURUSD"],
        timeframe="M15",
    )

    plan = await adapter.plan(objective)
    strategies = await adapter.build_strategies(objective, seed=42)

    assert plan["execution"] == "research_only"
    assert strategies[0].generation_source == "HERMES"
    assert strategies[0].symbols == ["EURUSD"]


async def test_production_hermes_runs_locally_without_a_model() -> None:
    router = cast(ModelRouter, cast(Any, StubRouter()))
    stub = cast(Any, router)
    stub.status = lambda: {
        "configured": True,
        "provider": "mock",
        "model": "deterministic-mock",
        "base_url": "",
        "api_key_present": False,
        "secret_storage": "LOCAL_0600",
    }
    adapter = ProductionHermesAdapter(router)
    objective = ResearchObjective(
        title="Local research",
        thesis="Test a deterministic strategy generator without an AI provider.",
        symbols=["EURUSD"],
        timeframe="M15",
    )

    plan = await adapter.plan(objective)
    strategies = await adapter.build_strategies(objective, seed=42)

    assert adapter.verified is True
    assert adapter.name == LocalResearchAdapter.name
    assert plan["planner"] == "local-deterministic-research"
    assert len(strategies) == 3
    assert {strategy.generation_source for strategy in strategies} == {"LOCAL_ENGINE"}
