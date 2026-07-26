from qforge.optimizer import select_portfolio
from qforge.risk import review_risk
from qforge.schemas import (
    BacktestMetrics,
    BacktestResult,
    Mode,
    StatisticalResult,
    utc_now,
)


def test_human_approval_cannot_override_a_demo_account_failure() -> None:
    metrics = BacktestMetrics(
        net_return=0.1,
        annualized_return=0.1,
        maximum_drawdown=0.05,
        sharpe_ratio=1.2,
        sortino_ratio=1.5,
        calmar_ratio=2.0,
        profit_factor=1.4,
        expectancy=12.0,
        win_rate=0.55,
        average_win=25.0,
        average_loss=-15.0,
        consecutive_losses=3,
        exposure=0.3,
        turnover=0.8,
        number_of_trades=30,
        time_in_market=0.3,
        recovery_factor=2.0,
        monthly_return_distribution={},
        regime_performance={"high_volatility": 0.01, "normal": 0.01},
    )
    backtest = BacktestResult(
        strategy_id="S-001",
        seed=42,
        started_at=utc_now(),
        completed_at=utc_now(),
        assumptions={},
        metrics=metrics,
        trades=[],
        equity_curve=[100_000, 110_000],
    )
    statistics = [
        StatisticalResult(
            strategy_id="S-001",
            robustness_score=0.8,
            overfitting_risk=0.2,
            execution_realism_score=0.9,
            regime_stability_score=0.9,
            deployment_recommendation="PAPER",
            rejection_reasons=[],
        )
    ]
    selection = select_portfolio(statistics, seed=42)
    decision = review_risk(
        [backtest],
        statistics,
        selection,
        human_approved=True,
        target_mode=Mode.MT5_DEMO,
        demo_account_verified=False,
    )
    assert decision.eligible
    assert not decision.approved
    assert "demo_account_verified" in decision.rejection_reasons
