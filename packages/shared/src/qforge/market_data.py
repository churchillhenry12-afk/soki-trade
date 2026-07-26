from __future__ import annotations

from pathlib import Path
from time import time
from typing import ClassVar, Protocol

import httpx
import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class MarketDataAdapter(Protocol):
    name: str
    verified: bool

    def bars(self, symbol: str, timeframe: str, *, seed: int) -> pd.DataFrame: ...


def validate_bars(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"market data is missing columns: {sorted(missing)}")
    result = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    if not result["timestamp"].is_monotonic_increasing:
        raise ValueError("market data timestamps must be strictly ordered")
    if result["timestamp"].duplicated().any():
        raise ValueError("market data timestamps must be unique")
    if result[list(REQUIRED_COLUMNS[1:])].isna().any().any():
        raise ValueError("market data contains missing numeric values")
    open_close = result.loc[:, ["open", "close"]]
    invalid_ohlc = (
        (result["high"] < open_close.max(axis="columns"))
        | (result["low"] > open_close.min(axis="columns"))
        | (result["low"] > result["high"])
    )
    if invalid_ohlc.any():
        raise ValueError("market data contains invalid OHLC relationships")
    return result


class MockMarketDataAdapter:
    name = "mock-synthetic-ohlcv"
    verified = False

    def bars(self, symbol: str, timeframe: str, *, seed: int) -> pd.DataFrame:
        del symbol, timeframe
        rng = np.random.default_rng(seed)
        count = 1_500
        regimes = np.repeat([0.00002, -0.00001, 0.00004, -0.000025, 0.000015], 300)
        cycle = np.sin(np.arange(count) / 18.0) * 0.00008
        shocks = rng.normal(0, 0.00032, count)
        returns = regimes + cycle + shocks
        close = 1.08 * np.exp(np.cumsum(returns))
        open_price = np.r_[close[0], close[:-1]]
        intrabar = np.abs(rng.normal(0.00028, 0.00008, count))
        high = np.maximum(open_price, close) + intrabar
        low = np.minimum(open_price, close) - intrabar
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=count, freq="15min", tz="UTC"),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": rng.integers(80, 800, count),
            }
        )
        return validate_bars(frame)


class FileMarketDataAdapter:
    name = "csv-parquet"
    verified = True

    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory

    def bars(self, symbol: str, timeframe: str, *, seed: int) -> pd.DataFrame:
        del seed
        base = self.data_directory / f"{symbol}_{timeframe}"
        parquet_path = base.with_suffix(".parquet")
        csv_path = base.with_suffix(".csv")
        if parquet_path.exists():
            frame = pd.read_parquet(parquet_path)
        elif csv_path.exists():
            frame = pd.read_csv(csv_path)
        else:
            raise FileNotFoundError(f"no CSV or Parquet data found for {symbol} {timeframe}")
        return validate_bars(frame)


class YahooFinanceMarketDataAdapter:
    """Real public OHLCV feed with transparent local file caching."""

    name = "yahoo-finance+local-cache"
    verified = True

    _timeframes: ClassVar[dict[str, tuple[str, str, str | None]]] = {
        "M5": ("5m", "60d", None),
        "M15": ("15m", "60d", None),
        "M30": ("30m", "60d", None),
        "H1": ("60m", "730d", None),
        "H4": ("60m", "730d", "4h"),
        "D1": ("1d", "10y", None),
    }
    _crypto_bases: ClassVar[set[str]] = {
        "BTC",
        "ETH",
        "SOL",
        "XRP",
        "ADA",
        "DOGE",
        "BNB",
        "LTC",
    }

    def __init__(self, data_directory: Path, *, cache_ttl_seconds: int = 900) -> None:
        self.data_directory = data_directory
        self.files = FileMarketDataAdapter(data_directory)
        self.cache_directory = data_directory / ".cache"
        self.cache = FileMarketDataAdapter(self.cache_directory)
        self.cache_ttl_seconds = cache_ttl_seconds

    def bars(self, symbol: str, timeframe: str, *, seed: int) -> pd.DataFrame:
        del seed
        try:
            return self.files.bars(symbol, timeframe, seed=0)
        except FileNotFoundError:
            cache_path = self.cache_directory / f"{symbol}_{timeframe}.csv"
            cache_is_fresh = (
                cache_path.exists()
                and time() - cache_path.stat().st_mtime <= self.cache_ttl_seconds
            )
            if cache_is_fresh:
                return self.cache.bars(symbol, timeframe, seed=0)
            try:
                frame = self._download(symbol, timeframe)
                self._cache(symbol, timeframe, frame)
                return frame
            except (httpx.HTTPError, ValueError):
                if cache_path.exists():
                    return self.cache.bars(symbol, timeframe, seed=0)
                raise

    def _download(self, symbol: str, timeframe: str) -> pd.DataFrame:
        try:
            interval, range_name, resample = self._timeframes[timeframe]
        except KeyError as error:
            raise ValueError(f"unsupported public-feed timeframe: {timeframe}") from error
        feed_symbol = self._feed_symbol(symbol)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{feed_symbol}"
        with httpx.Client(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Soki-Trade/0.1 market-research"},
        ) as client:
            response = client.get(
                url,
                params={
                    "range": range_name,
                    "interval": interval,
                    "includePrePost": "false",
                    "events": "div,splits",
                },
            )
            response.raise_for_status()
        payload = response.json()
        try:
            result = payload["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError) as error:
            chart_error = payload.get("chart", {}).get("error")
            raise ValueError(f"public market feed returned no candles: {chart_error}") from error
        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
                "open": quote["open"],
                "high": quote["high"],
                "low": quote["low"],
                "close": quote["close"],
                "volume": quote.get("volume", [0] * len(timestamps)),
            }
        )
        frame["volume"] = frame["volume"].fillna(0)
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        if resample is not None:
            frame = (
                frame.set_index("timestamp")
                .resample(resample)
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna(subset=["open", "high", "low", "close"])
                .reset_index()
            )
        if len(frame) < 200:
            raise ValueError(
                f"public market feed returned only {len(frame)} usable candles for "
                f"{symbol} {timeframe}"
            )
        return validate_bars(frame)

    def _cache(self, symbol: str, timeframe: str, frame: pd.DataFrame) -> None:
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        path = self.cache_directory / f"{symbol}_{timeframe}.csv"
        temporary = path.with_suffix(".csv.tmp")
        frame.to_csv(temporary, index=False)
        temporary.replace(path)

    def _feed_symbol(self, symbol: str) -> str:
        normalized = symbol.upper()
        if normalized.endswith("USD") and normalized[:-3] in self._crypto_bases:
            return f"{normalized[:-3]}-USD"
        if len(normalized) == 6 and normalized.isalpha():
            return f"{normalized}=X"
        return normalized
