# Timeframes

The pipeline produces nine timeframes from the cleaned M1 data.

## Reference table

| Code  | Description      | pandas offset alias | Expected bars/year* | Recommended use                          |
|-------|------------------|---------------------|---------------------|------------------------------------------|
| M1    | 1 minute         | `1min` (base data)  | ~261,000            | Spread analysis, microstructure research |
| M5    | 5 minutes        | `5min`              | ~52,200             | Short-term intraday                      |
| M15   | 15 minutes       | `15min`             | ~17,400             | Intraday session analysis                |
| H1    | 1 hour           | `1h`                | ~4,350              | Swing / intraday strategy development    |
| H4    | 4 hours          | `4h`                | ~1,090              | Multi-day regime detection               |
| H12   | 12 hours         | `12h`               | ~365                | Session-level analysis                   |
| D1    | 1 day            | `1D`                | ~261                | Trend / fundamental overlays             |
| W1    | 1 week           | `1W`                | ~52                 | Weekly momentum, position sizing         |
| MN1   | 1 month (start)  | `1MS`               | ~12                 | Macro cycle analysis                     |

*Expected bars/year assumes 24/5 forex market schedule, excluding weekends and
public holidays. Gold trades approximately 261 days per year at full liquidity.

## Resampling parameters (pandas)

```python
agg = {
    "open":          "first",
    "high":          "max",
    "low":           "min",
    "close":         "last",
    "tick_volume":   "sum",
    "real_volume":   "sum",
    "spread_points": "mean",
    "spread_pips":   "mean",
}

df.resample(freq, label="left", closed="left").agg(agg).dropna(how="all")
```

`label="left"` means each bar is labelled with its **open** time (the left
boundary of the interval), consistent with MT5 convention.
`closed="left"` means the interval is `[start, end)`.
Empty bars (e.g., weekends in D1+) are dropped with `.dropna(how="all")`.

## Output layout

```
data/processed/parquet/
  clean_5y/
    M1/year=2020/part-0.parquet
    M1/year=2021/part-0.parquet
    ...
    MN1/part-0.parquet      # single file for weekly and monthly
  extended/
    M1/year=2020/part-0.parquet
    ...

data/processed/xauusd.duckdb   # tables: xauusd_m1 ... xauusd_mn1
```

## DuckDB table naming

| Timeframe | DuckDB table name |
|-----------|-------------------|
| M1        | `xauusd_m1`       |
| M5        | `xauusd_m5`       |
| M15       | `xauusd_m15`      |
| H1        | `xauusd_h1`       |
| H4        | `xauusd_h4`       |
| H12       | `xauusd_h12`      |
| D1        | `xauusd_d1`       |
| W1        | `xauusd_w1`       |
| MN1       | `xauusd_mn1`      |

## When to use each timeframe

**M1 / M5:** Microstructure research, spread distribution analysis, tick-level
reconstruction. Not suitable for trend strategies due to noise.

**M15 / H1:** Classic intraday strategy development. Good balance between
signal quality and data volume.

**H4 / H12:** Swing trading regime detection, session-based patterns. Reduces
noise significantly while retaining intraday structure.

**D1:** Daily bar strategies, fundamental-technical overlays, volatility regime
labelling. The workhorse for most quantitative finance research.

**W1 / MN1:** Macro trend analysis, portfolio allocation signals. Few bars per
year — useful as reference, not primary signal.

## Further reading

- pandas resample documentation:
  https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.resample.html
- pandas time series offset aliases:
  https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases
