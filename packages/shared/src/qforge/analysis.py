from __future__ import annotations

import pandas as pd

from qforge.backtester import ExecutionAssumptions, run_backtest
from qforge.schemas import (
    AdversarialResult,
    BacktestResult,
    Critique,
    StatisticalResult,
    StrategyDefinition,
)


def criticize(result: BacktestResult) -> Critique:
    weaknesses: list[str] = []
    metrics = result.metrics
    if metrics.number_of_trades < 30:
        weaknesses.append("small_sample_size")
    if metrics.maximum_drawdown > 0.12:
        weaknesses.append("elevated_drawdown")
    if metrics.profit_factor < 1.05:
        weaknesses.append("weak_profit_factor")
    if (
        abs(metrics.regime_performance["high_volatility"] - metrics.regime_performance["normal"])
        > 0.01
    ):
        weaknesses.append("regime_dependency")
    if metrics.consecutive_losses >= 6:
        weaknesses.append("loss_clustering")
    severity = "HIGH" if len(weaknesses) >= 3 else "MEDIUM" if weaknesses else "LOW"
    return Critique(strategy_id=result.strategy_id, weaknesses=weaknesses, severity=severity)


def run_adversarial_tests(
    strategy: StrategyDefinition,
    baseline: BacktestResult,
    frame: pd.DataFrame,
    *,
    seed: int,
) -> list[AdversarialResult]:
    results: list[AdversarialResult] = []
    for spread_multiplier, slippage_multiplier in ((1.5, 1.5), (2.0, 2.0), (3.0, 3.0)):
        stressed = run_backtest(
            strategy,
            frame,
            seed=seed,
            assumptions=ExecutionAssumptions(
                spread_multiplier=spread_multiplier,
                slippage_multiplier=slippage_multiplier,
            ),
        )
        baseline_return = baseline.metrics.net_return
        degradation = baseline_return - stressed.metrics.net_return
        results.append(
            AdversarialResult(
                strategy_id=strategy.strategy_id,
                spread_multiplier=spread_multiplier,
                slippage_multiplier=slippage_multiplier,
                stressed_return=stressed.metrics.net_return,
                degradation=degradation,
                passed=stressed.metrics.net_return > -0.03 and degradation < 0.08,
            )
        )
    return results


def score_robustness(
    backtest: BacktestResult,
    critique: Critique,
    attacks: list[AdversarialResult],
) -> StatisticalResult:
    metrics = backtest.metrics
    stress_pass_rate = sum(attack.passed for attack in attacks) / max(len(attacks), 1)
    trade_score = min(metrics.number_of_trades / 60, 1.0)
    drawdown_score = max(0.0, 1 - metrics.maximum_drawdown / 0.2)
    profit_score = min(max(metrics.profit_factor / 1.5, 0.0), 1.0)
    critique_penalty = {"LOW": 0.0, "MEDIUM": 0.12, "HIGH": 0.28}[critique.severity]
    robustness = max(
        0.0,
        min(
            1.0,
            0.25 * stress_pass_rate
            + 0.25 * trade_score
            + 0.25 * drawdown_score
            + 0.25 * profit_score
            - critique_penalty,
        ),
    )
    execution_realism = max(0.0, min(1.0, 0.4 + 0.6 * stress_pass_rate))
    regime_gap = abs(
        metrics.regime_performance["high_volatility"] - metrics.regime_performance["normal"]
    )
    regime_stability = max(0.0, min(1.0, 1 - regime_gap * 50))
    overfitting_risk = max(0.0, min(1.0, 1 - (trade_score + stress_pass_rate) / 2))
    reasons: list[str] = []
    if robustness < 0.55:
        reasons.append("robustness_below_threshold")
    if stress_pass_rate < 2 / 3:
        reasons.append("execution_stress_failed")
    recommendation = "PAPER" if not reasons else "RESEARCH" if robustness >= 0.35 else "REJECT"
    return StatisticalResult(
        strategy_id=backtest.strategy_id,
        robustness_score=robustness,
        overfitting_risk=overfitting_risk,
        execution_realism_score=execution_realism,
        regime_stability_score=regime_stability,
        deployment_recommendation=recommendation,
        rejection_reasons=reasons,
    )
