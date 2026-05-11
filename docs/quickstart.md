# Quickstart â€” from clone to figures in 5 steps

**Prerequisites:** Python 3.11+, pip, Git. (Optional: Docker)

---

## Step 1 â€” Clone and install

```bash
git clone https://github.com/MSeyyidDev/time-series-data-preparation.git
cd time-series-data-preparation
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

## Step 2 â€” Place your raw data file

Copy your MT5 export to the expected location:

```
data/raw/XAUUSD_M1.csv
```

The file must be the MT5 tab-separated export with the header:

```
<DATE>	<TIME>	<OPEN>	<HIGH>	<LOW>	<CLOSE>	<TICKVOL>	<VOL>	<SPREAD>
```

If you want to run a quick smoke-test without real data first, skip to Step 5
(the test suite uses a synthetic fixture).

---

## Step 3 â€” Inspect the raw data

```bash
tsdataprep inspect --input data/raw/XAUUSD_M1.csv
```

This prints row count, date range, spread statistics, and flags any obvious
data quality issues. No files are written.

---

## Step 4 â€” Run the full pipeline

```bash
tsdataprep run-all \
    --input data/raw/XAUUSD_M1.csv \
    --out data/processed
```

This runs all six stages (inspect â†’ clean â†’ normalize â†’ resample â†’ export â†’
visualize) and writes:

```
data/processed/
  parquet/clean_5y/{M1,M5,...,MN1}/year=YYYY/part-0.parquet
  parquet/extended/{M1,M5,...,MN1}/year=YYYY/part-0.parquet
  xauusd.duckdb
  quality_report.json
  manifest.json

reports/figures/
  price_overview.png
  spread_before_after.png
  flash_crash_2021_08_09.png
  report.html              (interactive Plotly report)
```

Expected runtime on a modern laptop: **3â€“8 minutes** for the full 2.2 M-row
dataset.

---

## Step 5 â€” Verify with the test suite

```bash
pytest -q
```

All tests use the synthetic 10k-row fixture in `tests/fixtures/sample_m1.csv`
and do not require the real data file. All tests should pass on a clean install.

---

## Running with Docker

If you prefer to run the pipeline in a container (no local Python install needed):

```bash
# Build the image once
docker build -t tsdataprep:latest .

# Run the full pipeline (data/ is mounted from the host)
docker compose up etl
```

The container writes outputs to `./data/processed/` and `./reports/figures/`
on your host machine.

---

## Running individual pipeline stages

You can run each stage independently:

```bash
# Clean only (writes clean M1 Parquet)
tsdataprep clean --input data/raw/XAUUSD_M1.csv --out data/processed

# Resample (reads clean M1 Parquet, writes all timeframes)
tsdataprep resample --input data/processed --out data/processed

# Export to DuckDB
tsdataprep export --parquet data/processed/parquet --duckdb data/processed/xauusd.duckdb

# Generate figures
tsdataprep visualize --parquet data/processed/parquet --out reports/figures
```

---

## Querying the output with DuckDB

```python
import duckdb

con = duckdb.connect("data/processed/xauusd.duckdb")

# Daily bars for 2023
df = con.execute("""
    SELECT ts, open, high, low, close, spread_pips
    FROM xauusd_d1
    WHERE ts >= '2023-01-01'
    ORDER BY ts
""").df()

print(df.head())
```

Or from the command line:

```bash
duckdb data/processed/xauusd.duckdb \
    "SELECT COUNT(*), MIN(ts), MAX(ts) FROM xauusd_h1"
```

