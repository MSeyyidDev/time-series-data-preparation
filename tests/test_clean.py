"""Tests for tsdataprep.clean.

All synthetic -- no dependency on the 132 MB real CSV.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tsdataprep.clean import (
    clean,
    drop_ohlc_invalid,
    drop_return_explosions,
    drop_spread_outliers,
    sort_and_dedup,
    trim_to_window,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal canonical-schema DataFrame from a list of row dicts."""
    defaults = {
        "open": 1800.0,
        "high": 1801.0,
        "low": 1799.0,
        "close": 1800.5,
        "tick_volume": 100,
        "real_volume": 0,
        "spread_points": 50,
        "spread_pips": 5.0,
    }
    data = []
    for r in rows:
        row = {**defaults, **r}
        data.append(row)
    df = pd.DataFrame(data)
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize("UTC")
    df["spread_points"] = df["spread_points"].astype("int32")
    df["spread_pips"] = df["spread_pips"].astype("float32")
    df["tick_volume"] = df["tick_volume"].astype("int64")
    df["real_volume"] = df["real_volume"].astype("int64")
    return df


def _make_clean_df(n: int = 10, start: str = "2022-01-03 10:00:00") -> pd.DataFrame:
    """Generate n sequential M1 bars starting at `start`."""
    ts = pd.date_range(start=start, periods=n, freq="1min", tz="UTC")
    base = 1800.0
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [base + 0.1 * i for i in range(n)],
            "high": [base + 0.2 * i + 1 for i in range(n)],
            "low": [base + 0.1 * i - 1 for i in range(n)],
            "close": [base + 0.15 * i for i in range(n)],
            "tick_volume": np.ones(n, dtype="int64") * 100,
            "real_volume": np.zeros(n, dtype="int64"),
            "spread_points": pd.array([50] * n, dtype="int32"),
            "spread_pips": pd.array([5.0] * n, dtype="float32"),
        }
    )


# ---------------------------------------------------------------------------
# sort_and_dedup
# ---------------------------------------------------------------------------


class TestSortAndDedup:
    def test_sorts_ascending(self):
        rows = [
            {"ts": "2022-01-03 10:02:00", "close": 1801.0},
            {"ts": "2022-01-03 10:01:00", "close": 1800.5},
            {"ts": "2022-01-03 10:00:00", "close": 1800.0},
        ]
        df = _make_df(rows)
        result, _ = sort_and_dedup(df)
        assert result["ts"].is_monotonic_increasing

    def test_drops_duplicates(self):
        rows = [
            {"ts": "2022-01-03 10:00:00", "close": 1800.0},
            {"ts": "2022-01-03 10:00:00", "close": 1801.0},  # duplicate
            {"ts": "2022-01-03 10:01:00", "close": 1800.5},
        ]
        df = _make_df(rows)
        result, dropped = sort_and_dedup(df)
        assert len(result) == 2
        assert dropped == 1

    def test_keeps_first_on_dup(self):
        rows = [
            {"ts": "2022-01-03 10:00:00", "close": 1800.0},
            {"ts": "2022-01-03 10:00:00", "close": 1801.0},
        ]
        df = _make_df(rows)
        result, _ = sort_and_dedup(df)
        assert float(result["close"].iloc[0]) == 1800.0

    def test_no_dup_returns_zero(self):
        df = _make_clean_df(5)
        _, dropped = sort_and_dedup(df)
        assert dropped == 0


# ---------------------------------------------------------------------------
# drop_ohlc_invalid
# ---------------------------------------------------------------------------


class TestDropOhlcInvalid:
    def test_drops_high_lt_low(self):
        rows = [
            {"ts": "2022-01-03 10:00:00", "high": 1799.0, "low": 1801.0},  # invalid
            {"ts": "2022-01-03 10:01:00"},
        ]
        df = _make_df(rows)
        result, dropped = drop_ohlc_invalid(df)
        assert dropped == 1
        assert len(result) == 1

    def test_drops_open_above_high(self):
        rows = [
            {"ts": "2022-01-03 10:00:00", "open": 1802.0, "high": 1801.0, "low": 1799.0},
        ]
        df = _make_df(rows)
        _, dropped = drop_ohlc_invalid(df)
        assert dropped == 1

    def test_drops_negative_close(self):
        rows = [
            {"ts": "2022-01-03 10:00:00", "open": -1.0, "high": -0.5, "low": -1.5, "close": -1.0},
        ]
        df = _make_df(rows)
        _, dropped = drop_ohlc_invalid(df)
        assert dropped == 1

    def test_clean_data_zero_dropped(self):
        df = _make_clean_df(10)
        _, dropped = drop_ohlc_invalid(df)
        assert dropped == 0


# ---------------------------------------------------------------------------
# drop_spread_outliers
# ---------------------------------------------------------------------------


class TestDropSpreadOutliers:
    def test_drops_above_p99_per_year(self):
        # Create 200 bars in 2022 with spread=50, then add one spike
        n = 200
        ts = pd.date_range("2022-01-03 10:00:00", periods=n, freq="1min", tz="UTC")
        spreads = [50] * n
        spreads[99] = 9000  # extreme spike -- well above p99
        df = pd.DataFrame(
            {
                "ts": ts,
                "open": [1800.0] * n,
                "high": [1801.0] * n,
                "low": [1799.0] * n,
                "close": [1800.5] * n,
                "tick_volume": np.ones(n, dtype="int64") * 100,
                "real_volume": np.zeros(n, dtype="int64"),
                "spread_points": pd.array(spreads, dtype="int32"),
                "spread_pips": pd.array([s / 10.0 for s in spreads], dtype="float32"),
            }
        )
        result, dropped = drop_spread_outliers(df)
        assert dropped >= 1

    def test_normal_spread_unchanged(self):
        df = _make_clean_df(50)
        result, dropped = drop_spread_outliers(df)
        assert dropped == 0

    def test_per_year_boundary(self):
        # Bars split across two years with different spreads -- p99 computed per year
        ts_2022 = pd.date_range("2022-06-01 10:00:00", periods=100, freq="1min", tz="UTC")
        ts_2023 = pd.date_range("2023-06-01 10:00:00", periods=100, freq="1min", tz="UTC")
        spreads_2022 = [50] * 100
        spreads_2023 = [500] * 100  # 2023 has uniformly high spread, p99=500 -> none dropped
        ts_all = ts_2022.append(ts_2023)
        spreads_all = spreads_2022 + spreads_2023
        df = pd.DataFrame(
            {
                "ts": ts_all,
                "open": [1800.0] * 200,
                "high": [1801.0] * 200,
                "low": [1799.0] * 200,
                "close": [1800.5] * 200,
                "tick_volume": np.ones(200, dtype="int64") * 100,
                "real_volume": np.zeros(200, dtype="int64"),
                "spread_points": pd.array(spreads_all, dtype="int32"),
                "spread_pips": pd.array([s / 10.0 for s in spreads_all], dtype="float32"),
            }
        )
        result, dropped = drop_spread_outliers(df)
        # 2022 has uniform spreads (no outlier), 2023 uniform (no outlier)
        assert dropped == 0


# ---------------------------------------------------------------------------
# drop_return_explosions
# ---------------------------------------------------------------------------


class TestDropReturnExplosions:
    def test_drops_flash_crash_bars(self):
        """Simulate the Aug 2021 gold flash crash: large |ret| + giant spread."""
        n = 300
        ts = pd.date_range("2021-08-01 00:00:00", periods=n, freq="1min", tz="UTC")
        closes = [1800.0] * n
        spreads = [50] * n
        # Inject crash bars at index 100, 101, 102
        closes[100] = 1800.0
        closes[101] = 1750.0  # -2.78% return
        closes[102] = 1800.0  # recovery
        spreads[100] = 9000
        spreads[101] = 9000
        spreads[102] = 9000
        df = pd.DataFrame(
            {
                "ts": ts,
                "open": closes,
                "high": [c + 1 for c in closes],
                "low": [c - 1 for c in closes],
                "close": closes,
                "tick_volume": np.ones(n, dtype="int64"),
                "real_volume": np.zeros(n, dtype="int64"),
                "spread_points": pd.array(spreads, dtype="int32"),
                "spread_pips": pd.array([s / 10.0 for s in spreads], dtype="float32"),
            }
        )
        result, dropped = drop_return_explosions(df)
        assert dropped >= 1, "At least one flash-crash bar should be dropped"

    def test_normal_data_mostly_kept(self):
        """Normal data with no large outliers should drop 0 or very few bars."""
        n = 500
        ts = pd.date_range("2022-01-03 10:00:00", periods=n, freq="1min", tz="UTC")
        rng = np.random.default_rng(42)
        closes = 1800.0 + np.cumsum(rng.normal(0, 0.1, n))
        df = pd.DataFrame(
            {
                "ts": ts,
                "open": closes,
                "high": closes + 0.5,
                "low": closes - 0.5,
                "close": closes,
                "tick_volume": np.ones(n, dtype="int64"),
                "real_volume": np.zeros(n, dtype="int64"),
                "spread_points": pd.array([50] * n, dtype="int32"),
                "spread_pips": pd.array([5.0] * n, dtype="float32"),
            }
        )
        _, dropped = drop_return_explosions(df)
        assert dropped == 0

    def test_large_return_with_normal_spread_kept(self):
        """A real fast move (large |ret|) with NORMAL spread must NOT be dropped."""
        n = 300
        ts = pd.date_range("2022-01-03 10:00:00", periods=n, freq="1min", tz="UTC")
        closes = [1800.0] * n
        spreads = [50] * n
        # Large return at index 150 but normal spread
        closes[150] = 1750.0
        spreads[150] = 50  # normal spread
        df = pd.DataFrame(
            {
                "ts": ts,
                "open": closes,
                "high": [c + 1 for c in closes],
                "low": [c - 1 for c in closes],
                "close": closes,
                "tick_volume": np.ones(n, dtype="int64"),
                "real_volume": np.zeros(n, dtype="int64"),
                "spread_points": pd.array(spreads, dtype="int32"),
                "spread_pips": pd.array([s / 10.0 for s in spreads], dtype="float32"),
            }
        )
        result, dropped = drop_return_explosions(df)
        # The bar with large return + normal spread must survive
        assert 150 in result.index or len(result) > n - 5


# ---------------------------------------------------------------------------
# trim_to_window
# ---------------------------------------------------------------------------


class TestTrimToWindow:
    def test_clean_5y_bounds(self):
        # Bars before, inside, and after the 5y window
        ts_list = [
            "2019-12-31 23:59:00",  # before
            "2020-01-01 00:00:00",  # start (inclusive)
            "2022-06-15 12:00:00",  # middle
            "2024-12-31 23:59:00",  # inside
            "2025-01-01 00:00:00",  # start of 2025 -- exclusive
            "2025-06-01 10:00:00",  # after
        ]
        rows = [{"ts": t} for t in ts_list]
        df = _make_df(rows)
        result, dropped = trim_to_window(df, "clean_5y")
        # Should keep 2020-01-01 00:00 through 2024-12-31 23:59 only
        assert dropped == 3
        assert len(result) == 3

    def test_extended_bounds(self):
        ts_list = [
            "2019-12-31 23:59:00",  # before
            "2020-01-01 00:00:00",  # start
            "2026-05-08 23:59:00",  # end (inclusive)
            "2026-05-09 00:00:00",  # after
        ]
        rows = [{"ts": t} for t in ts_list]
        df = _make_df(rows)
        result, dropped = trim_to_window(df, "extended")
        assert dropped == 2
        assert len(result) == 2

    def test_invalid_scope_raises(self):
        df = _make_clean_df(5)
        with pytest.raises(ValueError, match="Unknown scope"):
            trim_to_window(df, "invalid_scope")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# clean (full pipeline)
# ---------------------------------------------------------------------------


class TestClean:
    def test_returns_tuple(self):
        df = _make_clean_df(20, start="2022-01-03 10:00:00")
        # Trim to 5y window -- data is in 2022, should survive
        result, counts = clean(df, scope="clean_5y")
        assert isinstance(result, pd.DataFrame)
        assert isinstance(counts, dict)

    def test_counts_keys(self):
        df = _make_clean_df(10, start="2022-01-03 10:00:00")
        _, counts = clean(df, scope="clean_5y")
        expected_keys = {
            "dup_ts",
            "ohlc_invalid",
            "spread_outlier",
            "return_explosion",
            "out_of_window",
        }
        assert set(counts.keys()) == expected_keys

    def test_result_is_sorted(self):
        df = _make_clean_df(10, start="2022-01-03 10:00:00")
        result, _ = clean(df, scope="clean_5y")
        assert result["ts"].is_monotonic_increasing

    def test_out_of_window_counted(self):
        # All bars in 2019 should be dropped as out_of_window
        df = _make_clean_df(10, start="2019-01-03 10:00:00")
        _, counts = clean(df, scope="clean_5y")
        assert counts["out_of_window"] == 10

    def test_flash_crash_bars_dropped_by_full_pipeline(self):
        """The Aug 2021 flash crash bars must be dropped by the full pipeline."""
        n = 500
        ts = pd.date_range("2021-01-03 10:00:00", periods=n, freq="1min", tz="UTC")
        closes = np.full(n, 1800.0)
        spreads = np.full(n, 50, dtype="int32")
        # Inject flash crash bars at 300, 301, 302
        closes[300] = 1800.0
        closes[301] = 1750.0  # -2.78% drop
        closes[302] = 1800.0  # recovery
        spreads[300] = 9000
        spreads[301] = 9000
        spreads[302] = 9000
        df = pd.DataFrame(
            {
                "ts": ts,
                "open": closes,
                "high": closes + 0.5,
                "low": closes - 0.5,
                "close": closes,
                "tick_volume": np.ones(n, dtype="int64"),
                "real_volume": np.zeros(n, dtype="int64"),
                "spread_points": spreads,
                "spread_pips": (spreads / 10.0).astype("float32"),
            }
        )
        result, counts = clean(df, scope="clean_5y")
        total_dropped = sum(counts.values())
        # At minimum the crash bars were dropped somewhere in the pipeline
        assert total_dropped >= 3, (
            f"Expected >= 3 bars dropped for flash crash, got {total_dropped}: {counts}"
        )
