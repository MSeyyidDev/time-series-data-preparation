"""Tests for tsdataprep.validate."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tsdataprep.validate import validate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_df(n: int = 20, spread_pips: float = 2.0) -> pd.DataFrame:
    """Return a small fully-valid canonical DataFrame."""
    ts = pd.date_range("2022-01-03 10:00:00", periods=n, freq="1min", tz="UTC")
    base = 1800.0
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [base] * n,
            "high": [base + 1.0] * n,
            "low": [base - 1.0] * n,
            "close": [base + 0.5] * n,
            "tick_volume": np.ones(n, dtype="int64") * 100,
            "real_volume": np.zeros(n, dtype="int64"),
            "spread_points": pd.array([int(spread_pips * 10)] * n, dtype="int32"),
            "spread_pips": pd.array([spread_pips] * n, dtype="float32"),
        }
    )


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------


class TestValidateHappy:
    def test_returns_dict(self):
        df = _make_valid_df()
        report = validate(df, scope="test")
        assert isinstance(report, dict)

    def test_all_checks_passed(self):
        df = _make_valid_df()
        report = validate(df, scope="test")
        assert report["all_checks_passed"] is True

    def test_n_rows_correct(self):
        df = _make_valid_df(15)
        report = validate(df, scope="test")
        assert report["n_rows"] == 15

    def test_scope_in_report(self):
        df = _make_valid_df()
        report = validate(df, scope="clean_5y")
        assert report["scope"] == "clean_5y"

    def test_date_range_present(self):
        df = _make_valid_df(10)
        report = validate(df, scope="test")
        assert "start" in report["date_range"]
        assert "end" in report["date_range"]

    def test_median_spread_pips_close_to_two(self):
        df = _make_valid_df(100, spread_pips=2.0)
        report = validate(df, scope="test")
        assert abs(report["median_spread_pips"] - 2.0) < 0.01


# ---------------------------------------------------------------------------
# Hard violation tests
# ---------------------------------------------------------------------------


class TestValidateHardViolations:
    def test_missing_column_raises(self):
        df = _make_valid_df()
        df = df.drop(columns=["close"])
        with pytest.raises(ValueError, match="Missing canonical columns"):
            validate(df)

    def test_non_monotonic_ts_raises(self):
        df = _make_valid_df(5)
        # Swap first two rows so ts is not monotonic
        idx = list(range(5))
        idx[0], idx[1] = 1, 0
        df = df.iloc[idx].reset_index(drop=True)
        with pytest.raises(ValueError, match="monotonically"):
            validate(df)

    def test_duplicate_ts_raises(self):
        df = _make_valid_df(5)
        dup = df.iloc[[0]].copy()
        df2 = pd.concat([df, dup]).reset_index(drop=True)
        # Sort to make it monotonic, then duplicate check should still fire
        with pytest.raises(ValueError):
            validate(df2)

    def test_nan_in_ohlc_raises(self):
        df = _make_valid_df(5)
        df.loc[2, "close"] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            validate(df)

    def test_ohlc_consistency_violation_raises(self):
        df = _make_valid_df(5)
        df.loc[0, "high"] = 1798.0  # high < low -> invalid
        with pytest.raises(ValueError, match="OHLC consistency"):
            validate(df)


# ---------------------------------------------------------------------------
# Soft warning tests
# ---------------------------------------------------------------------------


class TestValidateSoftWarnings:
    def test_spread_too_high_warns(self):
        """Spread of 100 pips (spread_points=1000) is way above band."""
        df = _make_valid_df(50, spread_pips=100.0)
        with pytest.warns(UserWarning, match="median spread_pips"):
            validate(df, scope="test")

    def test_spread_too_low_warns(self):
        """Spread of 0.1 pips is below band."""
        df = _make_valid_df(50, spread_pips=0.1)
        with pytest.warns(UserWarning, match="median spread_pips"):
            validate(df, scope="test")

    def test_spread_in_band_no_warning(self):
        """Median spread at 2.0 pips (within [1.5, 3.0]) should produce no warning."""
        df = _make_valid_df(50, spread_pips=2.0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validate(df, scope="test")
        spread_warns = [w for w in caught if "spread_pips" in str(w.message)]
        assert len(spread_warns) == 0
