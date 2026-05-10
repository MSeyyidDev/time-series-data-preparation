"""Clean normalized M1 XAUUSD data according to SHARED_SPEC §4.

All public functions accept and return DataFrames with the canonical schema.
Every dropped row is counted; callers accumulate the counters in a dict with
reason codes: ohlc_invalid, dup_ts, spread_outlier, return_explosion, out_of_window.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

Scope = Literal["clean_5y", "extended"]

# Date boundaries (inclusive at start, exclusive or inclusive at end per spec)
_WINDOW_START = pd.Timestamp("2020-01-01", tz="UTC")
_WINDOW_5Y_END_EXCL = pd.Timestamp("2025-01-01", tz="UTC")  # ts < this
_WINDOW_EXT_END_INCL = pd.Timestamp("2026-05-08 23:59:00", tz="UTC")  # ts <= this


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def sort_and_dedup(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Sort by ts ascending, drop exact duplicate timestamps keeping first.

    Returns (cleaned_df, n_dropped).
    """
    df = df.sort_values("ts").reset_index(drop=True)
    before = len(df)
    df = df.drop_duplicates(subset=["ts"], keep="first").reset_index(drop=True)
    return df, before - len(df)


def drop_ohlc_invalid(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop bars failing OHLC sanity checks.

    Rules:
    - high >= low
    - open and close both in [low, high]
    - all of open, high, low, close > 0
    Returns (cleaned_df, n_dropped).
    """
    mask_valid = (
        (df["high"] >= df["low"])
        & (df["open"] >= df["low"])
        & (df["open"] <= df["high"])
        & (df["close"] >= df["low"])
        & (df["close"] <= df["high"])
        & (df["open"] > 0)
        & (df["high"] > 0)
        & (df["low"] > 0)
        & (df["close"] > 0)
    )
    before = len(df)
    df = df[mask_valid].reset_index(drop=True)
    return df, before - len(df)


def drop_spread_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop bars where spread_points exceeds per-year 99th percentile.

    Year is derived from the ts column.
    Returns (cleaned_df, n_dropped).
    """
    df = df.copy()
    year = df["ts"].dt.year
    # Compute p99 per year and broadcast back
    p99 = df.groupby(year)["spread_points"].transform(lambda s: s.quantile(0.99))
    mask_keep = df["spread_points"] <= p99
    before = len(df)
    df = df[mask_keep].reset_index(drop=True)
    return df, before - len(df)


def drop_return_explosions(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop bars where |ret| > 8*MAD(ret) AND spread_points > global p95.

    MAD is scaled by 1.4826 to make it a robust sigma equivalent.
    Both conditions must hold simultaneously (spec §4 rule 4).
    Returns (cleaned_df, n_dropped).
    """
    df = df.copy()
    ret = df["close"].pct_change()

    mad_raw = (ret - ret.median()).abs().median()
    mad = mad_raw * 1.4826  # robust sigma

    p95_spread = df["spread_points"].quantile(0.95)

    # Condition A: |ret| > 8 * MAD
    cond_ret = ret.abs() > 8 * mad
    # Condition B: spread above p95
    cond_spread = df["spread_points"] > p95_spread

    # Drop only rows where BOTH conditions hold
    mask_drop = cond_ret & cond_spread
    df = df[~mask_drop].reset_index(drop=True)
    return df, int(mask_drop.sum())


def trim_to_window(df: pd.DataFrame, scope: Scope) -> tuple[pd.DataFrame, int]:
    """Trim DataFrame to the date window defined by scope.

    clean_5y : 2020-01-01 <= ts < 2025-01-01
    extended : 2020-01-01 <= ts <= 2026-05-08 23:59
    Returns (trimmed_df, n_dropped).
    """
    before = len(df)
    if scope == "clean_5y":
        mask = (df["ts"] >= _WINDOW_START) & (df["ts"] < _WINDOW_5Y_END_EXCL)
    elif scope == "extended":
        mask = (df["ts"] >= _WINDOW_START) & (df["ts"] <= _WINDOW_EXT_END_INCL)
    else:
        raise ValueError(f"Unknown scope: {scope!r}")
    df = df[mask].reset_index(drop=True)
    return df, before - len(df)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def clean(
    df: pd.DataFrame,
    scope: Scope,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Run the full cleaning pipeline on a normalized M1 DataFrame.

    Steps (in order):
    1. Sort + dedup timestamps
    2. OHLC sanity checks
    3. Per-year spread p99 outlier filter
    4. Return-explosion filter (|ret|>8*MAD AND spread>p95)
    5. Trim to date window for the given scope
    6. spread_pips already present from normalize step (no-op here)

    Returns (clean_df, dropped_counts) where dropped_counts keys are:
    dup_ts, ohlc_invalid, spread_outlier, return_explosion, out_of_window.
    """
    counts: dict[str, int] = {
        "dup_ts": 0,
        "ohlc_invalid": 0,
        "spread_outlier": 0,
        "return_explosion": 0,
        "out_of_window": 0,
    }

    df, counts["dup_ts"] = sort_and_dedup(df)
    df, counts["ohlc_invalid"] = drop_ohlc_invalid(df)
    df, counts["spread_outlier"] = drop_spread_outliers(df)
    df, counts["return_explosion"] = drop_return_explosions(df)
    df, counts["out_of_window"] = trim_to_window(df, scope)

    return df, counts
