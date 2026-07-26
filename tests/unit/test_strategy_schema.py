import pytest
from pydantic import ValidationError
from qforge.schemas import (
    ConditionGroup,
    ExitRules,
    IndicatorCondition,
    RiskRules,
    StrategyDefinition,
)


def valid_strategy() -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="EURUSD-M15-TEST",
        name="Typed crossover",
        symbols=["EURUSD"],
        timeframe="M15",
        entry=ConditionGroup(
            conditions=[
                IndicatorCondition(
                    indicator="EMA",
                    period=8,
                    comparison="crosses_above",
                    target_indicator="EMA",
                    target_period=21,
                )
            ]
        ),
        exit=ExitRules(stop_loss_atr=1.5, take_profit_atr=2.5),
        risk=RiskRules(risk_per_trade=0.005),
        generation_source="HUMAN",
    )


def test_strategy_dsl_accepts_valid_typed_strategy() -> None:
    assert valid_strategy().strategy_id == "EURUSD-M15-TEST"


def test_strategy_dsl_rejects_excess_trade_risk() -> None:
    payload = valid_strategy().model_dump()
    payload["risk"]["risk_per_trade"] = 0.01
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(payload)


def test_strategy_dsl_rejects_arbitrary_code_fields() -> None:
    payload = valid_strategy().model_dump()
    payload["python"] = "import os"
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(payload)
