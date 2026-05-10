"""Tests for tsdataprep.normalize."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tsdataprep.normalize import (
    add_spread_pips,
    build_utc_ts,
    enforce_dtypes,
    normalize,
    rename_columns,
    strip_angle_brackets,
)


def _make_raw_df(n: int = 3) -> pd.DataFrame:
    """Return a small raw MT5-style DataFrame (with angle-bracketed names)."""
    dates = [f"2022.01.0{i + 1}" for i in range(n)]
    times = ["10:00:00"] * n
    return pd.DataFrame(
        {
            "<DATE>": dates,
            "<TIME>": times,
            "<OPEN>": [1800.0 + i for i in range(n)],
            "<HIGH>": [1801.0 + i for i in range(n)],
            "<LOW>": [1799.0 + i for i in range(n)],
            "<CLOSE>": [1800.5 + i for i in range(n)],
            "<TICKVOL>": [100 + i for i in range(n)],
            "<VOL>": [0] * n,
            "<SPREAD>": [50 + i for i in range(n)],
        }
    )


class TestStripAngleBrackets:
    def test_basic(self):
        cols = ["<DATE>", "<TIME>", "<OPEN>"]
        assert strip_angle_brackets(cols) == ["DATE", "TIME", "OPEN"]

    def test_no_brackets(self):
        cols = ["DATE", "OPEN"]
        assert strip_angle_brackets(cols) == ["DATE", "OPEN"]

    def test_partial_brackets(self):
        cols = ["<DATE>", "OPEN"]
        assert strip_angle_brackets(cols) == ["DATE", "OPEN"]


class TestBuildUtcTs:
    def test_returns_utc_series(self):
        df = pd.DataFrame({"DATE": ["2022.01.03"], "TIME": ["10:00:00"]})
        ts = build_utc_ts(df)
        assert str(ts.dt.tz) == "UTC"

    def test_correct_value(self):
        df = pd.DataFrame({"DATE": ["2022.01.03"], "TIME": ["10:00:00"]})
        ts = build_utc_ts(df)
        expected = pd.Timestamp("2022-01-03 10:00:00", tz="UTC")
        assert ts.iloc[0] == expected

    def test_length(self):
        df = pd.DataFrame(
            {
                "DATE": ["2022.01.03", "2022.01.04"],
                "TIME": ["10:00:00", "11:00:00"],
            }
        )
        ts = build_utc_ts(df)
        assert len(ts) == 2


class TestRenameColumns:
    def test_rename_ohlc(self):
        df = pd.DataFrame(
            {
                "DATE": [],
                "TIME": [],
                "OPEN": [],
                "HIGH": [],
                "LOW": [],
                "CLOSE": [],
                "TICKVOL": [],
                "VOL": [],
                "SPREAD": [],
            }
        )
        result = rename_columns(df)
        assert "open" in result.columns
        assert "tick_volume" in result.columns
        assert "real_volume" in result.columns
        assert "spread_points" in result.columns


class TestAddSpreadPips:
    def test_value(self):
        df = pd.DataFrame({"spread_points": pd.array([100, 50, 200], dtype="int32")})
        result = add_spread_pips(df)
        assert "spread_pips" in result.columns
        np.testing.assert_allclose(result["spread_pips"].values, [10.0, 5.0, 20.0], rtol=1e-5)

    def test_dtype_float32(self):
        df = pd.DataFrame({"spread_points": pd.array([100], dtype="int32")})
        result = add_spread_pips(df)
        assert result["spread_pips"].dtype == "float32"

    def test_does_not_mutate_input(self):
        df = pd.DataFrame({"spread_points": pd.array([100], dtype="int32")})
        _ = add_spread_pips(df)
        assert "spread_pips" not in df.columns


class TestEnforceDtypes:
    def test_casts_float_columns(self):
        df = pd.DataFrame(
            {
                "open": [1800],
                "high": [1801],
                "low": [1799],
                "close": [1800.5],
                "tick_volume": [100],
                "real_volume": [0],
                "spread_points": [50],
                "spread_pips": [5.0],
            }
        )
        result = enforce_dtypes(df)
        assert result["open"].dtype == "float64"
        assert result["spread_points"].dtype == "int32"
        assert result["spread_pips"].dtype == "float32"


class TestNormalize:
    def test_returns_canonical_columns(self):
        df = _make_raw_df()
        result = normalize(df)
        expected_cols = [
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
        assert list(result.columns) == expected_cols

    def test_ts_is_utc(self):
        df = _make_raw_df()
        result = normalize(df)
        assert str(result["ts"].dt.tz) == "UTC"

    def test_no_date_time_columns(self):
        df = _make_raw_df()
        result = normalize(df)
        assert "DATE" not in result.columns
        assert "TIME" not in result.columns

    def test_spread_pips_formula(self):
        df = _make_raw_df(1)
        result = normalize(df)
        expected = float(result["spread_points"].iloc[0]) / 10.0
        assert abs(float(result["spread_pips"].iloc[0]) - expected) < 1e-4

    def test_row_count_preserved(self):
        df = _make_raw_df(5)
        result = normalize(df)
        assert len(result) == 5

    def test_dtypes_canonical(self):
        df = _make_raw_df(3)
        result = normalize(df)
        assert result["open"].dtype == "float64"
        assert result["tick_volume"].dtype == "int64"
        assert result["spread_points"].dtype == "int32"
        assert result["spread_pips"].dtype == "float32"
