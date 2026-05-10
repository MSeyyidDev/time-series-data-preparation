"""Tests for tsdataprep.resample -- synthetic data only, must run in < 10 s."""
# ruff: noqa: E402, I001  -- path-bootstrap pattern requires imports after sys.path insert

from __future__ import annotations

# ── path bootstrap ────────────────────────────────────────────────────────────
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from tsdataprep.resample import _cast_dtypes, _write_parquet, resample_m1, write_duckdb  # noqa: E402

# ── fixtures ──────────────────────────────────────────────────────────────────


def _make_m1(n: int = 1440, start: str = "2022-01-03 00:00") -> pd.DataFrame:
    """Create a synthetic M1 DataFrame with n bars."""
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC", name="ts")
    rng = pd.Series(range(n))
    df = pd.DataFrame(
        {
            "ts": idx,
            "open": 1800.0 + rng * 0.01,
            "high": 1800.5 + rng * 0.01,
            "low": 1799.5 + rng * 0.01,
            "close": 1800.2 + rng * 0.01,
            "tick_volume": (50 + rng % 100).astype("int64"),
            "real_volume": pd.array([0] * n, dtype="int64"),
            "spread_points": pd.array([20] * n, dtype="float32"),
            "spread_pips": pd.array([2.0] * n, dtype="float32"),
        }
    )
    return df


# ── unit tests ────────────────────────────────────────────────────────────────


class TestResampleM1:
    """resample_m1 unit tests."""

    def test_passthrough(self) -> None:
        df = _make_m1(100)
        out = resample_m1(df.copy(), "M1")
        assert len(out) == 100
        assert "ts" in out.columns

    def test_m5_reduces_rows(self) -> None:
        df = _make_m1(300)
        out = resample_m1(df.copy(), "M5")
        # 300 M1 bars -> 60 M5 bars (+ possibly 1 partial)
        assert len(out) <= 60
        assert len(out) > 0

    def test_h1_reduces_rows(self) -> None:
        df = _make_m1(1440)
        out = resample_m1(df.copy(), "H1")
        assert len(out) == 24

    def test_d1_from_one_day(self) -> None:
        df = _make_m1(1440)
        out = resample_m1(df.copy(), "D1")
        assert len(out) >= 1

    def test_monotonically_decreasing(self) -> None:
        """Row counts should decrease as timeframe widens."""
        df = _make_m1(10_080)  # 1 week of M1
        counts: dict[str, int] = {}
        tfs_to_test = ["M1", "M5", "M15", "H1", "H4", "D1"]
        for tf in tfs_to_test:
            out = resample_m1(df.copy(), tf)
            counts[tf] = len(out)
        prev = None
        for tf in tfs_to_test:
            if prev is not None:
                assert counts[tf] <= prev, f"{tf} ({counts[tf]}) > previous ({prev})"
            prev = counts[tf]

    def test_output_columns(self) -> None:
        df = _make_m1(100)
        out = resample_m1(df.copy(), "H1")
        expected = {
            "ts",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "real_volume",
            "spread_points",
            "spread_pips",
        }
        assert expected.issubset(set(out.columns))

    def test_high_ge_low(self) -> None:
        df = _make_m1(480)
        out = resample_m1(df.copy(), "H1")
        assert (out["high"] >= out["low"]).all()

    def test_volume_sum(self) -> None:
        df = _make_m1(60)
        out = resample_m1(df.copy(), "H1")
        # 60 M1 bars -> 1 H1 bar; tick_volume should be sum
        total_tv = df["tick_volume"].sum()
        assert int(out["tick_volume"].iloc[0]) == total_tv

    def test_spread_mean(self) -> None:
        df = _make_m1(60)
        out = resample_m1(df.copy(), "H1")
        expected = df["spread_points"].mean()
        assert abs(float(out["spread_points"].iloc[0]) - expected) < 0.01

    def test_mn1_alias(self) -> None:
        df = _make_m1(n=3 * 31 * 1440, start="2022-01-03 00:00")  # ~3 months
        out = resample_m1(df.copy(), "MN1")
        assert len(out) >= 1

    def test_w1_alias(self) -> None:
        df = _make_m1(n=7 * 1440, start="2022-01-03 00:00")  # 1 week
        out = resample_m1(df.copy(), "W1")
        assert len(out) >= 1

    def test_unknown_tf_raises(self) -> None:
        df = _make_m1(100)
        with pytest.raises((ValueError, KeyError)):
            resample_m1(df.copy(), "X99")

    def test_sorted_ascending(self) -> None:
        df = _make_m1(300)
        out = resample_m1(df.copy(), "H1")
        assert out["ts"].is_monotonic_increasing


class TestWriteParquet:
    """_write_parquet round-trip tests."""

    def test_year_partitioned(self, tmp_path: Path) -> None:
        df = _make_m1(1440)
        _write_parquet(df, tmp_path, "H1")
        year_dirs = list(tmp_path.glob("year=*"))
        assert len(year_dirs) >= 1
        parquet_files = list(tmp_path.glob("**/*.parquet"))
        assert len(parquet_files) >= 1

    def test_flat_w1(self, tmp_path: Path) -> None:
        df = _make_m1(10)
        _write_parquet(df, tmp_path, "W1")
        part = tmp_path / "part-0.parquet"
        assert part.exists()

    def test_flat_mn1(self, tmp_path: Path) -> None:
        df = _make_m1(10)
        _write_parquet(df, tmp_path, "MN1")
        part = tmp_path / "part-0.parquet"
        assert part.exists()

    def test_roundtrip(self, tmp_path: Path) -> None:
        import pyarrow.parquet as pq

        df = _make_m1(1440)
        _write_parquet(df, tmp_path, "H1")
        loaded = pq.read_table(str(tmp_path)).to_pandas()
        assert len(loaded) == 1440


@pytest.mark.skipif(
    sys.platform == "win32" and sys.version_info >= (3, 13),
    reason="DuckDB 1.3.x triggers a Windows access violation on Python 3.13 during pytest "
    "tmp_path teardown. Real pipeline runs (Python 3.11 in Docker / CI) are unaffected.",
)
class TestWriteDuckDB:
    """write_duckdb integration test with synthetic Parquet."""

    def test_tables_created(self, tmp_path: Path) -> None:

        parquet_dir = tmp_path / "parquet"
        db_path = tmp_path / "test.duckdb"

        # Write a tiny synthetic Parquet for H1 / clean_5y
        tf_dir = parquet_dir / "clean_5y" / "H1" / "year=2022"
        tf_dir.mkdir(parents=True)
        df = _make_m1(24)
        df_h1 = resample_m1(df.copy(), "H1")
        _write_parquet(df_h1, parquet_dir / "clean_5y" / "H1", "H1")

        tables = write_duckdb(parquet_dir, db_path, scopes=["clean_5y"], timeframes=["H1"])
        assert "xauusd_h1_clean_5y" in tables

        import duckdb

        con = duckdb.connect(str(db_path), read_only=True)
        cnt = con.execute("SELECT COUNT(*) FROM xauusd_h1_clean_5y").fetchone()[0]
        con.close()
        assert cnt > 0

    def test_missing_dir_skipped(self, tmp_path: Path) -> None:
        """write_duckdb should not crash on missing directories."""
        parquet_dir = tmp_path / "empty_parquet"
        parquet_dir.mkdir()
        db_path = tmp_path / "empty.duckdb"
        # Should not raise
        tables = write_duckdb(parquet_dir, db_path, scopes=["clean_5y"], timeframes=["M1"])
        assert isinstance(tables, list)


class TestCastDtypes:
    def test_basic(self) -> None:
        df = _make_m1(10)
        out = _cast_dtypes(df)
        assert out["open"].dtype == "float64"
        assert out["tick_volume"].dtype == "int64"
        assert out["spread_points"].dtype == "float32"
