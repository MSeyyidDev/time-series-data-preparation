"""Normalize raw MT5 XAUUSD M1 data to the canonical schema.

Assumption: the MT5 broker clock is UTC (or very close -- see docstring on
`build_utc_ts`).  No timezone shift is applied.  Document in quality report.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

# Canonical dtype map after normalization
CANONICAL_DTYPES: dict[str, Any] = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "tick_volume": "int64",
    "real_volume": "int64",
    "spread_points": "int32",
    "spread_pips": "float32",
}


def strip_angle_brackets(columns: list[str]) -> list[str]:
    """Remove leading/trailing angle brackets from MT5 column names."""
    return [c.strip("<>") for c in columns]


def build_utc_ts(df: pd.DataFrame) -> pd.Series:
    """Combine DATE and TIME columns into a UTC-aware datetime Series.

    The MT5 file header uses broker time.  Per the SHARED_SPEC assumption this
    is treated as UTC without any shift.  If the broker is on EET (UTC+2/+3)
    the caller must apply a timezone offset *before* invoking this function.
    This pipeline does NOT perform that shift -- it is documented here so future
    work can handle it by pre-processing `df['DATE']` and `df['TIME']`.
    """
    combined = df["DATE"].astype(str) + " " + df["TIME"].astype(str)
    ts = pd.to_datetime(combined, format="%Y.%m.%d %H:%M:%S", utc=False)
    return ts.dt.tz_localize("UTC")


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename stripped MT5 column names to the canonical schema."""
    rename_map = {
        "DATE": "DATE",  # kept temporarily for ts construction
        "TIME": "TIME",
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "TICKVOL": "tick_volume",
        "VOL": "real_volume",
        "SPREAD": "spread_points",
    }
    return df.rename(columns=rename_map)


def add_spread_pips(df: pd.DataFrame) -> pd.DataFrame:
    """Add spread_pips = spread_points / 10 (XAUUSD CFD convention)."""
    df = df.copy()
    df["spread_pips"] = (df["spread_points"] / 10.0).astype("float32")
    return df


def enforce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Cast each column to its canonical dtype; warn on lossy casts."""
    df = df.copy()
    for col, dtype in CANONICAL_DTYPES.items():
        if col in df.columns:
            try:
                df[col] = df[col].astype(dtype)
            except (ValueError, TypeError) as exc:
                warnings.warn(f"dtype cast failed for {col}: {exc}", stacklevel=2)
    return df


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Full normalization pipeline: rename, build UTC ts, add spread_pips, enforce dtypes.

    Input df must have the raw MT5 columns (with or without angle brackets).
    Returns a DataFrame with canonical schema, indexed by integer, ts as first column.
    """
    df = df.copy()
    # Strip angle brackets
    df.columns = strip_angle_brackets(list(df.columns))
    # Rename to canonical names
    df = rename_columns(df)
    # Build UTC timestamp
    df["ts"] = build_utc_ts(df)
    # Drop raw date/time columns
    df = df.drop(columns=["DATE", "TIME"])
    # Add spread_pips
    df = add_spread_pips(df)
    # Enforce dtypes
    df = enforce_dtypes(df)
    # Reorder columns to canonical order
    col_order = [
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
    df = df[col_order].reset_index(drop=True)
    return df
