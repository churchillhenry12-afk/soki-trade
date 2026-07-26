from qforge.agents import MockHermesAdapter
from qforge.backtester import run_backtest
from qforge.market_data import MockMarketDataAdapter
from qforge.schemas import ResearchObjective


async def test_backtest_is_seed_reproducible_and_never_exits_on_entry_bar() -> None:
    objective = ResearchObjective(
        title="Reproducible study",
        thesis="Test a deterministic strategy against deterministic generated bars.",
        symbols=["EURUSD"],
        timeframe="M15",
    )
    strategy = (await MockHermesAdapter().build_strategies(objective, seed=17))[0]
    frame = MockMarketDataAdapter().bars("EURUSD", "M15", seed=17)
    first = run_backtest(strategy, frame, seed=17)
    second = run_backtest(strategy, frame, seed=17)

    assert first.metrics == second.metrics
    assert first.equity_curve == second.equity_curve
    assert all(trade.bars_held >= 1 for trade in first.trades)
