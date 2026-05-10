"""Tests for tsdataprep.io: CSV load, Parquet write/read, SHA-256."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tsdataprep.io import (
    compute_file_sha256,
    load_raw_csv,
    read_parquet,
    write_parquet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_csv(tmp_path: Path) -> Path:
    """Write a tiny valid MT5-format TSV and return its path."""
    content = (
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2022.01.03\t10:00:00\t1800.00\t1801.00\t1799.00\t1800.50\t100\t0\t50\n"
        "2022.01.03\t10:01:00\t1800.50\t1802.00\t1800.00\t1801.00\t120\t0\t50\n"
    )
    p = tmp_path / "test.csv"
    p.write_text(content, encoding="utf-8")
    return p


def _make_canonical_df() -> pd.DataFrame:
    """Return a small canonical-schema DataFrame."""
    ts = pd.to_datetime(["2022-01-03 10:00:00", "2022-01-03 10:01:00"]).tz_localize("UTC")
    return pd.DataFrame({
        "ts": ts,
        "open":  [1800.0, 1800.5],
        "high":  [1801.0, 1802.0],
        "low":   [1799.0, 1800.0],
        "close": [1800.5, 1801.0],
        "tick_volume":  pd.array([100, 120], dtype="int64"),
        "real_volume":  pd.array([0, 0],   dtype="int64"),
        "spread_points": pd.array([50, 50], dtype="int32"),
        "spread_pips": pd.array([5.0, 5.0], dtype="float32"),
    })


# ---------------------------------------------------------------------------
# Tests: load_raw_csv
# ---------------------------------------------------------------------------

class TestLoadRawCsv:
    def test_returns_dataframe(self, tmp_path):
        p = _make_minimal_csv(tmp_path)
        df = load_raw_csv(p)
        assert isinstance(df, pd.DataFrame)

    def test_row_count(self, tmp_path):
        p = _make_minimal_csv(tmp_path)
        df = load_raw_csv(p)
        assert len(df) == 2

    def test_columns_present(self, tmp_path):
        p = _make_minimal_csv(tmp_path)
        df = load_raw_csv(p)
        assert "<DATE>" in df.columns
        assert "<SPREAD>" in df.columns

    def test_spread_dtype(self, tmp_path):
        p = _make_minimal_csv(tmp_path)
        df = load_raw_csv(p)
        assert df["<SPREAD>"].dtype == "int32"

    def test_close_dtype(self, tmp_path):
        p = _make_minimal_csv(tmp_path)
        df = load_raw_csv(p)
        assert df["<CLOSE>"].dtype == "float64"


# ---------------------------------------------------------------------------
# Tests: write_parquet / read_parquet
# ---------------------------------------------------------------------------

class TestParquetRoundTrip:
    def test_roundtrip_row_count(self, tmp_path):
        df = _make_canonical_df()
        p = tmp_path / "out.parquet"
        write_parquet(df, p)
        df2 = read_parquet(p)
        assert len(df2) == len(df)

    def test_roundtrip_columns(self, tmp_path):
        df = _make_canonical_df()
        p = tmp_path / "out.parquet"
        write_parquet(df, p)
        df2 = read_parquet(p)
        assert list(df2.columns) == list(df.columns)

    def test_ts_tz_utc(self, tmp_path):
        df = _make_canonical_df()
        p = tmp_path / "out.parquet"
        write_parquet(df, p)
        df2 = read_parquet(p)
        assert df2["ts"].dt.tz is not None
        assert str(df2["ts"].dt.tz) == "UTC"

    def test_parquet_file_created(self, tmp_path):
        df = _make_canonical_df()
        p = tmp_path / "sub" / "out.parquet"
        write_parquet(df, p)
        assert p.exists()
        assert p.stat().st_size > 0

    def test_deterministic_output(self, tmp_path):
        df = _make_canonical_df()
        p1 = tmp_path / "a.parquet"
        p2 = tmp_path / "b.parquet"
        write_parquet(df, p1)
        write_parquet(df, p2)
        # Both files should have identical bytes (deterministic compression)
        assert p1.read_bytes() == p2.read_bytes()

    def test_spread_pips_float32(self, tmp_path):
        df = _make_canonical_df()
        p = tmp_path / "out.parquet"
        write_parquet(df, p)
        df2 = read_parquet(p)
        assert df2["spread_pips"].dtype == "float32"


# ---------------------------------------------------------------------------
# Tests: compute_file_sha256
# ---------------------------------------------------------------------------

class TestSha256:
    def test_known_hash(self, tmp_path):
        p = tmp_path / "f.bin"
        data = b"hello world"
        p.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_sha256(p) == expected

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.bin"
        p.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_file_sha256(p) == expected

    def test_large_file_chunked(self, tmp_path):
        # 3 MB file -- forces multiple 1 MB chunks
        p = tmp_path / "big.bin"
        data = b"x" * (3 * 1024 * 1024)
        p.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_sha256(p) == expected

    def test_returns_hex_string(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"abc")
        result = compute_file_sha256(p)
        assert isinstance(result, str)
        assert len(result) == 64
