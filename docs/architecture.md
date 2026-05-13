# Architecture

## Pipeline overview

The pipeline is a linear, deterministic ETL that runs entirely in-process.
No streaming, no distributed compute - the 132 MB source file fits in RAM.

```
Raw MT5 export (tab-separated CSV)
          |
          v
  +-----------------+
  |   io.py         |  parse_raw()
  |      |  - reads tab-separated CSV
  |                 |  - parses <DATE>+<TIME> -> UTC timestamp
  |                 |  - renames columns to canonical schema
  +-----------------+
          |
          v
  +-----------------+
  |   clean.py      |  clean_m1()
  |      |  - OHLC sanity check (high>=low, open/close in range)
  |                 |  - spread outlier filter (per-year p99)
  |                 |  - return explosion filter (MAD-based)
  |                 |  - logs every dropped row to quality_report.json
  +-----------------+
          |
          v
  +-----------------+
  |  normalize.py   |  normalize()
  |      |  - adds spread_pips = spread_points / 10
  |                 |  - validates median spread in [1.5, 3.0] pips
  +-----------------+
          |
          v
  +-----------------+
  |  validate.py    |  validate()
  |      |  - schema conformance check
  |                 |  - monotonic timestamp check
  |                 |  - emits warnings for any violation
  +-----------------+
          |
          v  (clean M1 DataFrame, two scopes: clean_5y / extended)
  +-----------------+
  |  resample.py    |  resample_all()
  |      |  - produces M5, M15, H1, H4, H12, D1, W1, MN1
  |                 |  - aggregation: first/max/min/last/sum/mean
  |                 |  - label="left", closed="left"
  +-----------------+
          |
          v
  +-----------------+
  |  resample.py    |  write_parquet() + write_duckdb()
  |      |  - Hive-partitioned Parquet (year=YYYY)
  |                 |  - Single DuckDB file, one table per timeframe
  |                 |  - compression=zstd, level=3 (deterministic)
  +-----------------+
          |
          v
  +-----------------+
  | visualize.py    |  generate_figures()
  |      |  - price_overview.png (full OHLC)
  |                 |  - spread_before_after.png
  |                 |  - flash_crash_2021_08_09.png
  |                 |  - Optional: interactive HTML report
  +-----------------+
          |
          v
  reports/figures/  +  data/processed/manifest.json
```

## Module map

```
src/tsdataprep/
  __init__.py       package init, exports VERSION
  cli.py            Typer CLI - six subcommands
  config.py         constants, paths, scope definitions
  io.py             parse_raw(), load_parquet()
  clean.py          clean_m1(), drop_* helpers
  normalize.py      normalize(), validate_spread_median()
  validate.py       validate_schema(), validate_monotonic()
  resample.py       resample_all(), write_parquet(), write_duckdb()
  visualize.py      generate_figures(), flash_crash_zoom()

scripts/
  01_inspect.py     standalone quick-stats
  02_clean.py       standalone clean step
  03_resample.py    standalone resample step
  04_visualize.py   standalone visualize step

tests/
  conftest.py       shared fixtures: synthetic_m1_df, tmp_data_dir
  test_io.py
  test_clean.py
  test_normalize.py
  test_validate.py
  test_resample.py
  test_visualize.py
  fixtures/
    sample_m1.csv   1 000-row synthetic MT5 data
```

## Data flow details

### Timestamp handling

Raw MT5 data uses broker time (EET / UTC+2 with DST).
`io.parse_raw()` converts to UTC by subtracting 2 hours (no DST table lookup -
this is a known simplification; the broker's DST schedule matches Central
European Time).

### Two scopes

Every downstream consumer receives two labelled DataFrames:

| scope      | date range                         | primary use            |
|------------|------------------------------------|------------------------|
| `clean_5y` | 2020-01-01 to 2024-12-31 inclusive | modelling, backtesting |
| `extended` | 2020-01-01 to 2026-05-08 23:59     | current-state analysis |

### Determinism guarantee

Fixed seed is not required for this pipeline (no randomness).
Parquet row-group size is pinned at 100 000 rows; zstd compression level 3.
The manifest records input sha256 and package versions so any output can be
reproduced exactly from the same input.

## Dependency graph

```
cli.py
  +-- config.py
  +-- io.py
        +-- (pandas, pyarrow)
  +-- clean.py
        +-- io.py, (numpy)
  +-- normalize.py
        +-- clean.py
  +-- validate.py
        +-- normalize.py
  +-- resample.py
        +-- validate.py, (duckdb, pyarrow)
  +-- visualize.py
        +-- resample.py, (matplotlib, plotly)
```

