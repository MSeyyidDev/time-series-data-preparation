# Data Sources

## 1. Raw market data — MetaTrader 5 XAUUSD M1 export

**File:** `data/raw/XAUUSD_M1.csv`
**Format:** Tab-separated values (`.csv` extension despite the tab delimiter)
**Date range:** 2020-01-02 10:00 to 2026-05-08 23:54
**Rows:** approximately 2,234,266
**Provider:** Broker demo account via MetaTrader 5

### Column specification

The MT5 bar-export format uses angle-bracket-wrapped column names in the header:

```
<DATE>  <TIME>  <OPEN>  <HIGH>  <LOW>  <CLOSE>  <TICKVOL>  <VOL>  <SPREAD>
```

| Raw column  | Canonical name  | Description                                                 |
|-------------|-----------------|-------------------------------------------------------------|
| `<DATE>`    | part of `ts`    | Date in `YYYY.MM.DD` format                                 |
| `<TIME>`    | part of `ts`    | Time in `HH:MM:SS` format (broker time / EET UTC+2)        |
| `<OPEN>`    | `open`          | Bar open price (USD per troy ounce, 2 decimal places)       |
| `<HIGH>`    | `high`          | Bar high price                                              |
| `<LOW>`     | `low`           | Bar low price                                               |
| `<CLOSE>`   | `close`         | Bar close price                                             |
| `<TICKVOL>` | `tick_volume`   | Number of tick changes during the bar                       |
| `<VOL>`     | `real_volume`   | Traded volume in contracts (0 for most FX/CFD instruments)  |
| `<SPREAD>`  | `spread_points` | Spread in MT5 points (1 point = $0.01 for XAUUSD)          |

**Source:** MetaQuotes MQL5 community — historical data export format discussion:
- https://www.mql5.com/en/forum/227308 — "How to export quotes from MetaTrader 5?"
- https://strategyquant.com/doc/quantdatamanager/how-to-export-data-from-metatrader-5/ — StrategyQuant MT5 export guide

---

## 2. XAUUSD price and pip convention

For gold CFD instruments quoted in USD with two decimal places (e.g. 1923.45):

- **1 MT5 point** = $0.01 (the smallest price increment)
- **1 pip** = $0.10 = 10 points (the conventional CFD gold pip)
- Therefore: `spread_pips = spread_points / 10`

A spread of 20 points = 2 pips, which is a typical quoted spread for gold
during liquid hours.

**Sources:**
- Ultima Markets academy — "What is 1 Pip in XAUUSD? How to Calculate?":
  https://www.ultimamarkets.com/academy/what-is-1-pip-in-xauusd-how-to-calculate/
- Traders Union glossary — "How to Calculate Pips in XAU/USD":
  https://tradersunion.com/trading-glossary/what-is-xauusd/how-to-calculate-pips/

*Note: The LBMA Gold Price is a benchmark for physical gold, not CFD pip conventions.
The pip definition above follows the standard CFD broker convention uniformly used
across MetaTrader 5 brokers for XAUUSD.*

---

## 3. August 2021 gold flash crash

On **9 August 2021**, XAUUSD experienced a flash crash during the Asian trading
session, dropping approximately $80 (from ~$1,764 to a low of ~$1,678) within a
few minutes starting around 01:57 UTC+2.

**Contributing factors:**
- Stronger-than-expected US nonfarm payrolls (943k actual vs 870k forecast)
- Thin liquidity — Japanese markets closed for Mountain Day public holiday
- Cascading stop-loss orders around the $1,700 technical level

**Data impact in this project:**
The event produces `spread_points` values up to 9,000 and a `ret_1m` return of
approximately -2.7% in a single bar — far outside normal trading conditions. The
cleaning pipeline drops these bars using the combined spread-outlier and
return-explosion filter (spec rules 3 and 4). The zoom figure
`reports/figures/flash_crash_2021_08_09.png` shows the raw vs cleaned spread
distribution around the event window.

**Sources:**
- FX Empire — "Gold Bounces Off $1,678; The Low of the August 2021 Flash Crash":
  https://www.fxempire.com/forecasts/article/gold-bounces-off-1678-the-low-of-the-august-2021-flash-crash-1072038
- MarketPulse by OANDA — "Breaking: The Metals Market — Gold (XAU/USD) and
  Silver (XAG/USD) flash crash":
  https://www.marketpulse.com/news/breaking-the-metals-market-gold-xauusd-and-silver-xagusd-flash-crash/
- Piyush Ratnu analysis — "Why Spot Gold crashed on 09 August 2021":
  https://www.piyushratnu.com/why-spot-gold-crashed-on-09-august-2021/

---

## 4. Output formats

### Apache Parquet

Parquet is an open-source, column-oriented binary file format optimised for
analytical read patterns. This project writes Hive-partitioned Parquet
(year=YYYY sub-directories) compressed with zstd at level 3 via PyArrow.

**Source:** Apache Parquet official documentation:
https://parquet.apache.org/docs/

### DuckDB

DuckDB is an in-process OLAP SQL engine. The pipeline writes all timeframes as
separate tables into a single `.duckdb` file, enabling fast analytical queries
without a server process.

**Source:** DuckDB official documentation:
https://duckdb.org/docs/current/

### pandas resample

Resampling uses `pandas.DataFrame.resample` with `label="left"` and
`closed="left"` and the offset aliases defined in the pandas time-series guide.

**Source:** pandas time series / date functionality documentation:
https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html
