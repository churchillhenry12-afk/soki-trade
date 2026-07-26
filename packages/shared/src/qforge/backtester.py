from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from time import perf_counter
from typing import Literal

import numpy as np
import pandas as pd

from qforge.schemas import BacktestMetrics, BacktestResult, StrategyDefinition, Trade, utc_now


@dataclass(frozen=True)
class ExecutionAssumptions:
    initial_equity: float = 100_000.0
    spread: float = 0.00012
    slippage: float = 0.00002
    commission_rate: float = 0.00001
    spread_multiplier: float = 1.0
    slippage_multiplier: float = 1.0


@dataclass
class Position:
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    entry_index: int
    entry_time: datetime
    size: float
    stop: float
    target: float


def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1).rolling(period, min_periods=period).mean()


def _signal_frame(frame: pd.DataFrame, strategy: StrategyDefinition) -> pd.DataFrame:
    result = frame.copy()
    ema_conditions = [
        condition
        for condition in strategy.entry.conditions
        if condition.indicator == "EMA" and condition.target_indicator == "EMA"
    ]
    if not ema_conditions:
        raise ValueError("the milestone-one backtester requires one EMA cross condition")
    cross = ema_conditions[0]
    assert cross.target_period is not None
    fast = result["close"].ewm(span=cross.period, adjust=False).mean()
    slow = result["close"].ewm(span=cross.target_period, adjust=False).mean()
    atr_conditions = [
        condition for condition in strategy.entry.conditions if condition.indicator == "ATR"
    ]
    atr_period = atr_conditions[0].period if atr_conditions else 14
    atr_floor = atr_conditions[0].value if atr_conditions else 0.0
    result["atr"] = _atr(result, atr_period)
    volatility_ok = result["atr"] > float(atr_floor or 0.0)
    result["long_signal"] = (fast.shift(1) <= slow.shift(1)) & (fast > slow) & volatility_ok
    result["short_signal"] = (fast.shift(1) >= slow.shift(1)) & (fast < slow) & volatility_ok
    return result


def _maximum_consecutive_losses(trades: list[Trade]) -> int:
    longest = current = 0
    for trade in trades:
        current = current + 1 if trade.pnl < 0 else 0
        longest = max(longest, current)
    return longest


def _metrics(
    frame: pd.DataFrame,
    trades: list[Trade],
    equity_curve: list[float],
    initial_equity: float,
) -> BacktestMetrics:
    equity = np.asarray(equity_curve, dtype=float)
    net_return = float(equity[-1] / initial_equity - 1)
    running_max = np.maximum.accumulate(equity)
    drawdowns = equity / running_max - 1
    maximum_drawdown = float(abs(drawdowns.min()))
    bar_returns = np.diff(equity) / equity[:-1]
    nonzero = bar_returns[bar_returns != 0]
    periods_per_year = 365.25 * 24 * 4
    elapsed_years = max(len(frame) / periods_per_year, 1 / periods_per_year)
    annualized_return = float((max(equity[-1] / initial_equity, 1e-9) ** (1 / elapsed_years)) - 1)
    if nonzero.size > 1 and float(nonzero.std(ddof=1)) > 0:
        sharpe = float(nonzero.mean() / nonzero.std(ddof=1) * sqrt(periods_per_year))
    else:
        sharpe = 0.0
    downside = nonzero[nonzero < 0]
    if downside.size > 1 and float(downside.std(ddof=1)) > 0:
        sortino = float(nonzero.mean() / downside.std(ddof=1) * sqrt(periods_per_year))
    else:
        sortino = 0.0
    wins = [trade.pnl for trade in trades if trade.pnl > 0]
    losses = [trade.pnl for trade in trades if trade.pnl < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = float(gross_win / gross_loss) if gross_loss else float(gross_win > 0)
    expectancy = float(sum(trade.pnl for trade in trades) / len(trades)) if trades else 0.0
    win_rate = len(wins) / len(trades) if trades else 0.0
    average_win = float(np.mean(wins)) if wins else 0.0
    average_loss = float(np.mean(losses)) if losses else 0.0
    bars_held = sum(trade.bars_held for trade in trades)
    exposure = min(bars_held / len(frame), 1.0)
    turnover = float(sum(abs(trade.return_pct) for trade in trades))
    recovery = net_return / maximum_drawdown if maximum_drawdown else 0.0
    monthly: dict[str, float] = {}
    for trade in trades:
        month = trade.exit_time.strftime("%Y-%m")
        monthly[month] = monthly.get(month, 0.0) + trade.return_pct
    if trades:
        median_atr = float(_atr(frame, 14).median())
        high_vol = [
            trade.return_pct for trade in trades if abs(trade.entry_price - 1.08) > median_atr
        ]
        normal = [trade.return_pct for trade in trades if trade.return_pct not in high_vol]
    else:
        high_vol, normal = [], []
    return BacktestMetrics(
        net_return=net_return,
        annualized_return=annualized_return,
        maximum_drawdown=maximum_drawdown,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=annualized_return / maximum_drawdown if maximum_drawdown else 0.0,
        profit_factor=profit_factor,
        expectancy=expectancy,
        win_rate=win_rate,
        average_win=average_win,
        average_loss=average_loss,
        consecutive_losses=_maximum_consecutive_losses(trades),
        exposure=exposure,
        turnover=turnover,
        number_of_trades=len(trades),
        time_in_market=exposure,
        recovery_factor=recovery,
        monthly_return_distribution=monthly,
        regime_performance={
            "high_volatility": float(np.mean(high_vol)) if high_vol else 0.0,
            "normal": float(np.mean(normal)) if normal else 0.0,
        },
    )


def run_backtest(
    strategy: StrategyDefinition,
    frame: pd.DataFrame,
    *,
    seed: int,
    assumptions: ExecutionAssumptions | None = None,
) -> BacktestResult:
    started = utc_now()
    perf_counter()
    config = assumptions or ExecutionAssumptions()
    data = _signal_frame(frame, strategy)
    equity = config.initial_equity
    equity_curve = [equity]
    trades: list[Trade] = []
    pending: Literal["LONG", "SHORT"] | None = None
    position: Position | None = None
    spread = config.spread * config.spread_multiplier
    slippage = config.slippage * config.slippage_multiplier

    for index in range(1, len(data)):
        row = data.iloc[index]
        timestamp = row["timestamp"].to_pydatetime()

        if pending is not None and position is None and not np.isnan(row["atr"]):
            direction = pending
            price_adjustment = spread / 2 + slippage
            entry_price = float(row["open"]) + (
                price_adjustment if direction == "LONG" else -price_adjustment
            )
            stop_distance = float(row["atr"]) * strategy.exit.stop_loss_atr
            risk_amount = equity * strategy.risk.risk_per_trade
            size = risk_amount / max(stop_distance, 1e-9)
            position = Position(
                direction=direction,
                entry_price=entry_price,
                entry_index=index,
                entry_time=timestamp,
                size=size,
                stop=entry_price + (-stop_distance if direction == "LONG" else stop_distance),
                target=entry_price
                + (
                    float(row["atr"]) * strategy.exit.take_profit_atr
                    if direction == "LONG"
                    else -float(row["atr"]) * strategy.exit.take_profit_atr
                ),
            )
            pending = None

        if position is not None and index > position.entry_index:
            direction = position.direction
            entry_price = position.entry_price
            stop = position.stop
            target = position.target
            exit_price: float | None = None
            exit_reason: Literal["STOP", "TARGET", "TRAIL", "SIGNAL", "END"] | None = None
            if direction == "LONG":
                if float(row["low"]) <= stop:
                    exit_price, exit_reason = stop - spread / 2 - slippage, "STOP"
                elif float(row["high"]) >= target:
                    exit_price, exit_reason = target - spread / 2 - slippage, "TARGET"
            else:
                if float(row["high"]) >= stop:
                    exit_price, exit_reason = stop + spread / 2 + slippage, "STOP"
                elif float(row["low"]) <= target:
                    exit_price, exit_reason = target + spread / 2 + slippage, "TARGET"
            if exit_price is not None and exit_reason is not None:
                size = position.size
                raw_pnl = (
                    (exit_price - entry_price)
                    if direction == "LONG"
                    else (entry_price - exit_price)
                ) * size
                commission = (entry_price + exit_price) * size * config.commission_rate
                pnl = raw_pnl - commission
                before = equity
                equity += pnl
                trades.append(
                    Trade(
                        direction=direction,
                        entry_time=position.entry_time,
                        exit_time=timestamp,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        pnl=pnl,
                        return_pct=pnl / before,
                        bars_held=index - position.entry_index,
                        exit_reason=exit_reason,
                    )
                )
                position = None

        equity_curve.append(equity)
        if position is None and pending is None:
            long_allowed = strategy.allowed_direction in {"LONG", "BOTH"}
            short_allowed = strategy.allowed_direction in {"SHORT", "BOTH"}
            if bool(row["long_signal"]) and long_allowed:
                pending = "LONG"
            elif bool(row["short_signal"]) and short_allowed:
                pending = "SHORT"

    if position is not None:
        last = data.iloc[-1]
        direction = position.direction
        entry_price = position.entry_price
        exit_price = float(last["close"]) + (-spread / 2 if direction == "LONG" else spread / 2)
        size = position.size
        raw_pnl = (
            (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
        ) * size
        pnl = raw_pnl - (entry_price + exit_price) * size * config.commission_rate
        before = equity
        equity += pnl
        equity_curve[-1] = equity
        trades.append(
            Trade(
                direction=direction,
                entry_time=position.entry_time,
                exit_time=last["timestamp"].to_pydatetime(),
                entry_price=entry_price,
                exit_price=exit_price,
                pnl=pnl,
                return_pct=pnl / before,
                bars_held=len(data) - 1 - position.entry_index,
                exit_reason="END",
            )
        )

    return BacktestResult(
        strategy_id=strategy.strategy_id,
        seed=seed,
        started_at=started,
        completed_at=utc_now(),
        assumptions={
            "fill_model": "next_bar_conservative",
            "spread": spread,
            "slippage": slippage,
            "commission_rate": config.commission_rate,
        },
        metrics=_metrics(data, trades, equity_curve, config.initial_equity),
        trades=trades,
        equity_curve=[round(value, 6) for value in equity_curve],
    )
