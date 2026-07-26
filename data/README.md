# Production research data

SQLite metadata is stored here. In production, Soki Trade automatically downloads
real public candles and keeps a short-lived cache under `market/.cache/`.

You can override the public feed by placing your own CSV or Parquet file at the
matching `SYMBOL_TIMEFRAME` path. Local files always take precedence.

Required columns:

```text
timestamp,open,high,low,close,volume
```

Database and market-data files are ignored by Git. The public feed supports M5,
M15, M30, H1, H4 (resampled from H1), and D1. The first uncached request
requires internet access.
