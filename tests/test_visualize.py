"""Tests for tsdataprep.visualize -- synthetic data only, must run in < 10 s."""
# ruff: noqa: E402, I001  -- path-bootstrap pattern requires imports after sys.path insert

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# ── path bootstrap ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from tsdataprep.resample import _write_parquet, resample_m1  # noqa: E402
from tsdataprep.visualize import (  # noqa: E402
    _load_tf_scope,
    build_html_report,
    fig_flash_crash,
    fig_gap_heatmap,
    fig_price_overview,
    fig_rows_per_timeframe,
    fig_spread_before_after,
    fig_spread_pips_by_hour,
)

# ── fixtures ──────────────────────────────────────────────────────────────────


def _make_m1_full_year(n: int = 10_080) -> pd.DataFrame:
    """Create ~1 week of synthetic M1 data spanning 2021-08-08."""
    idx = pd.date_range("2021-08-08 12:00", periods=n, freq="1min", tz="UTC", name="ts")
    rng = pd.Series(range(n))
    return pd.DataFrame(
        {
            "ts": idx,
            "open": 1800.0 + rng * 0.001,
            "high": 1800.5 + rng * 0.001,
            "low": 1799.5 + rng * 0.001,
            "close": 1800.2 + rng * 0.001,
            "tick_volume": (50 + rng % 100).astype("int64"),
            "real_volume": pd.array([0] * n, dtype="int64"),
            "spread_points": pd.array([20] * n, dtype="float32"),
            "spread_pips": pd.array([2.0] * n, dtype="float32"),
        }
    )


def _build_parquet_tree(parquet_dir: Path, scope: str = "extended") -> dict[str, int]:
    """Build a minimal parquet tree for tests; return row counts per tf."""
    df_m1 = _make_m1_full_year()
    row_counts: dict[str, int] = {}
    for tf in ["M1", "M5", "H1", "W1", "D1", "MN1"]:
        df_tf = resample_m1(df_m1.copy(), tf)
        out_dir = parquet_dir / scope / tf
        _write_parquet(df_tf, out_dir, tf)
        row_counts[tf] = len(df_tf)
    return row_counts


# ── tests ─────────────────────────────────────────────────────────────────────


class TestFigPriceOverview:
    def test_produces_png(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        out = tmp_path / "price_overview.png"
        fig_price_overview(parquet_dir, out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_missing_data_no_crash(self, tmp_path: Path) -> None:
        """Should not raise if parquet dir is empty."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        out = tmp_path / "price_overview.png"
        fig_price_overview(empty_dir, out)  # should complete without exception


class TestFigSpreadBeforeAfter:
    def test_produces_png(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        out = tmp_path / "spread_before_after.png"
        # raw_csv doesn't exist -> only cleaned panel
        fig_spread_before_after(parquet_dir, tmp_path / "no_such.csv", out)
        assert out.exists()

    def test_missing_both_no_crash(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        out = tmp_path / "spread_before_after.png"
        fig_spread_before_after(empty_dir, tmp_path / "no.csv", out)
        # Just verifies no crash; file may or may not exist


class TestFigSpreadPipsByHour:
    def test_produces_png(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        out = tmp_path / "spread_pips_by_hour.png"
        fig_spread_pips_by_hour(parquet_dir, out)
        assert out.exists()
        assert out.stat().st_size > 500


class TestFigGapHeatmap:
    def test_produces_png(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        out = tmp_path / "gap_heatmap.png"
        fig_gap_heatmap(parquet_dir, out)
        assert out.exists()

    def test_no_crash_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        fig_gap_heatmap(empty, tmp_path / "gap.png")


class TestFigRowsPerTimeframe:
    def test_produces_png(self, tmp_path: Path) -> None:
        row_counts = {
            "clean_5y": {"M1": 100000, "M5": 20000, "H1": 5000, "D1": 365},
            "extended": {"M1": 150000, "M5": 30000, "H1": 7000, "D1": 550},
        }
        out = tmp_path / "rows_per_timeframe.png"
        fig_rows_per_timeframe(row_counts, out)
        assert out.exists()

    def test_empty_counts_no_crash(self, tmp_path: Path) -> None:
        out = tmp_path / "rows_per_timeframe.png"
        fig_rows_per_timeframe({}, out)


class TestFigFlashCrash:
    def test_produces_png_with_parquet_only(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        out = tmp_path / "flash_crash.png"
        fig_flash_crash(parquet_dir, tmp_path / "no.csv", out)
        assert out.exists()

    def test_no_crash_no_data(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        out = tmp_path / "flash_crash.png"
        fig_flash_crash(empty, tmp_path / "no.csv", out)


class TestBuildHtmlReport:
    def test_produces_html(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        row_counts_raw = _build_parquet_tree(parquet_dir, "extended")
        row_counts = {"extended": row_counts_raw, "clean_5y": row_counts_raw}
        out_html = tmp_path / "report.html"
        build_html_report(
            parquet_dir,
            tmp_path / "no.csv",
            row_counts,
            out_html,
        )
        assert out_html.exists()
        content = out_html.read_text(encoding="utf-8")
        assert "plotly" in content.lower() or "XAUUSD" in content
        assert "report.html" in str(out_html)

    def test_html_has_title(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        out_html = tmp_path / "report.html"
        build_html_report(parquet_dir, tmp_path / "no.csv", {}, out_html)
        content = out_html.read_text(encoding="utf-8")
        assert "<title>" in content


class TestLoadTfScope:
    def test_returns_none_for_missing(self, tmp_path: Path) -> None:
        result = _load_tf_scope(tmp_path / "no_such_dir", "extended", "M1")
        assert result is None

    def test_loads_written_parquet(self, tmp_path: Path) -> None:
        parquet_dir = tmp_path / "parquet"
        _build_parquet_tree(parquet_dir, "extended")
        df = _load_tf_scope(parquet_dir, "extended", "M1")
        assert df is not None
        assert len(df) > 0
        assert "ts" in df.columns
