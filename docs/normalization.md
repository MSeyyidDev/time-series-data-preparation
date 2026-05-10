# Normalization and Cleaning Rules

This document explains every cleaning rule applied to the raw XAUUSD M1 data,
the rationale behind each rule, and the effect on the spread distribution.

---

## Overview

The cleaning pipeline operates exclusively on the raw M1 bars **before**
resampling. The order of operations matters: rules run top-to-bottom, and each
step's output is the next step's input.

Every dropped row is logged to `data/processed/quality_report.json` with:
- `ts` — bar timestamp (UTC)
- `reason` — one of the reason codes below
- `spread_points`, `ret_1m` — diagnostic values

---

## Rule 1 — Parse and deduplicate

**What:** Merge `<DATE>` and `<TIME>` columns into a single UTC `ts` column.
Convert from broker time (EET / UTC+2) to UTC by subtracting 2 hours.
Sort ascending by `ts`. Drop exact duplicate timestamps (keep first occurrence).

**Why:** Downstream operations require a monotonically increasing, unique
DatetimeIndex. The MT5 export occasionally includes duplicate rows at DST
transitions or as broker artefacts.

**Reason code:** `duplicate_ts`

---

## Rule 2 — OHLC sanity check

**What:** Drop any bar where:
- `high < low`
- `open < low` or `open > high`
- `close < low` or `close > high`
- any of OHLC is <= 0

**Why:** These are logically impossible values that indicate data corruption.
Inspection of the 2020–2026 dataset found zero such bars, but the rule remains
as a defensive guard.

**Reason code:** `ohlc_invalid`

---

## Rule 3 — Spread outlier filter

**What:** For each calendar year, compute the 99th percentile of
`spread_points`. Drop any bar where `spread_points > p99(year)`.

**Why:** The spread widens dramatically during rollover windows (around midnight
broker time), low-liquidity sessions, and news events. These bars are not
tradeable at the quoted price and would distort downstream statistics.
Using a per-year threshold adapts to slowly changing liquidity regimes
(e.g., COVID-era spreads differed from 2024 spreads).

**Reason code:** `spread_outlier`

**Observed p99 values (approximate):**
| Year | p99 spread_points |
|------|-------------------|
| 2020 | ~320              |
| 2021 | ~400              |
| 2022 | ~280              |
| 2023 | ~250              |
| 2024 | ~240              |
| 2025 | ~230              |

---

## Rule 4 — Return-explosion filter (flash crash guard)

**What:** Compute `ret_1m = close.pct_change()`.
Calculate `MAD = median(|ret_1m - median(ret_1m)|)`.
Drop bars where **both** conditions hold:
1. `|ret_1m| > 8 * MAD`
2. `spread_points > p95(spread_points)` for that year

**Why:** A genuine fast move (e.g., NFP release) will have a large return but
a *normal* spread. The dual condition catches corrupted bars and genuine flash
crashes with abnormal spread, while preserving real high-volatility events.

The most notable event caught by this filter is the **August 9, 2021 flash crash**
(bars at 01:57–01:59 UTC+2): `ret_1m ≈ -2.7%`, `spread_points ≈ 9,000`.

**Reason code:** `return_explosion`

---

## Rule 5 — Date window trim

**What:** Restrict the cleaned dataset to:
- `clean_5y`: `2020-01-01 <= ts < 2025-01-01` (5 complete years)
- `extended`: `2020-01-01 <= ts <= 2026-05-08 23:59`

**Why:** The `clean_5y` scope provides five complete calendar years — a clean,
symmetric window suitable for backtesting and statistical analysis. The
`extended` scope captures everything available for current-state analysis.

**Reason code:** `out_of_window`

---

## Rule 6 — Spread normalization

**What:** Add `spread_pips = spread_points / 10.0`.

**Why:** CFD gold brokers conventionally quote spread in pips where 1 pip =
$0.10 = 10 MT5 points. Exposing both units avoids unit-confusion bugs in
downstream code.

**Validation:** After normalization, `median(spread_pips)` must fall in
`[1.5, 3.0]`. The validator raises a `ValueError` if this condition is not met.
This corresponds to the user's observed average spread of approximately 2 pips.

---

## Effect on spread distribution

The figures below show the spread distribution before and after cleaning.

**Before cleaning** (raw, all bars):
- Median spread: ~2 pips
- p99 spread: ~30–40 pips
- Maximum spread: ~900 pips (flash crash bars)

**After cleaning** (rules 3 + 6 applied):
- Median spread: ~2 pips (target: [1.5, 3.0] — validated)
- p99 spread: substantially reduced
- Tail is capped at per-year p99

![Spread distribution before and after cleaning](../reports/figures/spread_before_after.png)

*Figure: Histogram of spread_pips before cleaning (grey) and after cleaning (blue).
The long right tail — dominated by rollover and flash-crash bars — is removed.*

---

## Flash crash case study — 2021-08-09

The August 9, 2021 event is the most dramatic quality issue in the dataset.

![Flash crash zoom](../reports/figures/flash_crash_2021_08_09.png)

*Figure: XAUUSD M1 close price and spread_points around 2021-08-09 01:00–04:00 UTC+2.
The two flagged bars show spread_points > 9,000 and ret_1m near -2.7%.*

**What happened:** A combination of a better-than-expected US nonfarm payrolls
report, low Asian-session liquidity (Japanese market closed), and cascading
stop-loss orders drove gold from ~$1,764 to ~$1,678 in minutes before a partial
recovery to ~$1,726.

**Treatment:** Both bars at 01:57 and 01:58 satisfy both conditions of Rule 4
and are dropped. The gap is preserved — we do not synthesize fills.

**Source:** FX Empire — https://www.fxempire.com/forecasts/article/gold-bounces-off-1678-the-low-of-the-august-2021-flash-crash-1072038
