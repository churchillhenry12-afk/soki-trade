from __future__ import annotations

from dataclasses import dataclass

from qforge.schemas import (
    BacktestResult,
    Mode,
    RiskDecision,
    SolverResult,
    StatisticalResult,
)


@dataclass(frozen=True)
class ImmutableRiskRules:
    version: str = "2026-01"
    maximum_risk_per_trade: float = 0.005
    maximum_total_open_risk: float = 0.02
    maximum_strategy_drawdown: float = 0.20
    minimum_out_of_sample_trades: int = 10
    maximum_overfitting_risk: float = 0.65
    human_approval_required: bool = True
    live_trading_enabled: bool = False


DEFAULT_RISK_RULES = ImmutableRiskRules()


def review_risk(
    backtests: list[BacktestResult],
    statistics: list[StatisticalResult],
    selection: SolverResult,
    *,
    human_approved: bool = False,
    target_mode: Mode = Mode.PAPER,
    demo_account_verified: bool = False,
    rules: ImmutableRiskRules = DEFAULT_RISK_RULES,
) -> RiskDecision:
    selected_backtests = [
        result for result in backtests if result.strategy_id in selection.solution
    ]
    selected_statistics = [
        result for result in statistics if result.strategy_id in selection.solution
    ]
    checks = {
        "live_trading_disabled": not rules.live_trading_enabled,
        "portfolio_not_empty": bool(selection.solution),
        "drawdown_within_limit": bool(selected_backtests)
        and all(
            result.metrics.maximum_drawdown <= rules.maximum_strategy_drawdown
            for result in selected_backtests
        ),
        "minimum_trade_count": bool(selected_backtests)
        and all(
            result.metrics.number_of_trades >= rules.minimum_out_of_sample_trades
            for result in selected_backtests
        ),
        "overfitting_within_limit": bool(selected_statistics)
        and all(
            result.overfitting_risk <= rules.maximum_overfitting_risk
            for result in selected_statistics
        ),
        "stress_tests_passed": bool(selected_statistics)
        and all(
            "execution_stress_failed" not in result.rejection_reasons
            for result in selected_statistics
        ),
        "human_approval_present": human_approved,
        "demo_account_verified": target_mode != Mode.MT5_DEMO or demo_account_verified,
        "target_is_not_live": target_mode in {Mode.PAPER, Mode.MT5_DEMO},
    }
    evidence_checks = {
        key: value
        for key, value in checks.items()
        if key not in {"human_approval_present", "demo_account_verified"}
    }
    eligible = all(evidence_checks.values())
    approved = eligible and checks["human_approval_present"] and checks["demo_account_verified"]
    reasons = [name for name, passed in checks.items() if not passed]
    return RiskDecision(
        eligible=eligible,
        approved=approved,
        target_mode=target_mode,
        checks=checks,
        rejection_reasons=reasons,
        rules_version=rules.version,
    )
