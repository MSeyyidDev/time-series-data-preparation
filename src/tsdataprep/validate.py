"""Post-clean validation for the canonical M1 DataFrame.

Raises on hard schema violations; emits warnings.warn for soft issues.
Returns a structured report dict on success.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

# Acceptable median spread_pips band (spec sections 4 and 6)
SPREAD_PIPS_MEDIAN_MIN = 1.5
SPREAD_PIPS_MEDIAN_MAX = 3.0

REQUIRED_COLUMNS = [
    "ts",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "real_volume",
    "spread_points",
    "spread_pips",
]


def _assert_columns(df: pd.DataFrame) -> None:
    """Raise ValueError if any required column is missing."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing canonical columns: {missing}")


def _assert_ts_monotonic_unique(df: pd.DataFrame) -> None:
    """Raise ValueError if ts is not strictly monotonically increasing or has duplicates."""
    if not df["ts"].is_monotonic_increasing:
        raise ValueError("ts column is not monotonically increasing")
    if df["ts"].duplicated().any():
        raise ValueError("ts column contains duplicate values")


def _assert_no_ohlc_nan(df: pd.DataFrame) -> None:
    """Raise ValueError if any OHLC column contains NaN."""
    for col in ["open", "high", "low", "close"]:
        if df[col].isna().any():
            raise ValueError(f"NaN found in column {col!r}")


def _assert_ohlc_consistency(df: pd.DataFrame) -> None:
    """Raise ValueError if any bar violates high>=low or OHLC bounds."""
    bad = (
        (df["high"] < df["low"])
        | (df["open"] < df["low"])
        | (df["open"] > df["high"])
        | (df["close"] < df["low"])
        | (df["close"] > df["high"])
    )
    n_bad = int(bad.sum())
    if n_bad > 0:
        raise ValueError(f"OHLC consistency violated on {n_bad} bars")


def _check_spread_median(df: pd.DataFrame) -> dict[str, float]:
    """Warn if median spread_pips is outside [1.5, 3.0]; return spread stats."""
    median_sp = float(df["spread_pips"].median())
    mean_sp = float(df["spread_pips"].mean())
    if not (SPREAD_PIPS_MEDIAN_MIN <= median_sp <= SPREAD_PIPS_MEDIAN_MAX):
        warnings.warn(
            f"median spread_pips={median_sp:.3f} is outside [{SPREAD_PIPS_MEDIAN_MIN}, "
            f"{SPREAD_PIPS_MEDIAN_MAX}] -- check cleaning parameters",
            stacklevel=2,
        )
    return {"median_spread_pips": median_sp, "mean_spread_pips": mean_sp}


def validate(df: pd.DataFrame, *, scope: str = "unknown") -> dict[str, Any]:
    """Run all post-clean assertions and return a structured report dict.

    Hard violations raise ValueError immediately.
    Soft warnings (spread band) use warnings.warn.

    Returns a dict with keys: scope, n_rows, date_range, median_spread_pips,
    mean_spread_pips, all_checks_passed.
    """
    _assert_columns(df)
    _assert_ts_monotonic_unique(df)
    _assert_no_ohlc_nan(df)
    _assert_ohlc_consistency(df)

    spread_stats = _check_spread_median(df)

    ts_min = str(df["ts"].min())
    ts_max = str(df["ts"].max())

    report: dict[str, Any] = {
        "scope": scope,
        "n_rows": len(df),
        "date_range": {"start": ts_min, "end": ts_max},
        "median_spread_pips": spread_stats["median_spread_pips"],
        "mean_spread_pips": spread_stats["mean_spread_pips"],
        "all_checks_passed": True,
    }
    return report
