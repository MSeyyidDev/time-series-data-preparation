"""Visualization module: produce PNG figures + interactive HTML report.

Figures produced:
  1. price_overview.png         -- close price line (extended), log y, weekly down-sample
  2. spread_before_after.png    -- raw vs cleaned spread_points histograms
  3. spread_pips_by_hour.png    -- boxplot spread_pips by hour of day (cleaned)
  4. gap_heatmap.png            -- day-of-week × hour-of-day gap ratio
  5. rows_per_timeframe.png     -- bar chart rows per timeframe per scope
  6. flash_crash_2021_08_09.png -- close price 2021-08-08 18:00 -> 2021-08-09 04:00
  7. reports/report.html        -- single-file plotly HTML (figs 1, 2, 3 + summary table)
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib  # noqa: E402 (must precede pyplot import)

matplotlib.use("Agg")  # non-interactive backend

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .config import ALL_SCOPES, ALL_TFS, DATA_SOURCE_CAPTION, Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Matplotlib style
# ---------------------------------------------------------------------------

_STYLE = {
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.facecolor": "#fafafa",
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
    "font.size": 10,
}

_COLORS = {
    "clean_5y": "#2563EB",
    "extended": "#16A34A",
    "raw": "#DC2626",
    "cleaned": "#2563EB",
}


def _apply_style() -> None:
    matplotlib.rcParams.update(_STYLE)


def _add_caption(fig: plt.Figure) -> None:
    fig.text(
        0.99,
        0.01,
        DATA_SOURCE_CAPTION,
        ha="right",
        va="bottom",
        fontsize=7,
        color="#6B7280",
        transform=fig.transFigure,
    )


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _load_tf_scope(parquet_dir: Path, scope: str, tf: str) -> pd.DataFrame | None:
    """Load a timeframe/scope Parquet into a DataFrame; return None if missing."""
    tf_dir = parquet_dir / scope / tf
    if not tf_dir.exists():
        return None
    try:
        # pq.read_table handles nested directories
        table = pq.read_table(str(tf_dir))
        df = table.to_pandas()
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            df = df.sort_values("ts").reset_index(drop=True)
        return df
    except Exception as exc:
        logger.warning("Could not load %s/%s: %s", scope, tf, exc)
        return None


def _load_raw_m1(raw_csv: Path) -> pd.DataFrame | None:
    """Load raw CSV for flash-crash comparison figure."""
    if not raw_csv.exists():
        return None
    try:
        df = pd.read_csv(
            raw_csv,
            sep="\t",
            names=[
                "date",
                "time",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "real_volume",
                "spread_points",
            ],
            header=0,
        )
        ts_str = df["date"].str.replace(".", "-", regex=False) + " " + df["time"]
        df["ts"] = (
            pd.to_datetime(ts_str, format="%Y-%m-%d %H:%M:%S")
            .dt.tz_localize("Etc/GMT-2")
            .dt.tz_convert("UTC")
        )
        df = df.drop(columns=["date", "time"]).sort_values("ts").reset_index(drop=True)
        return df
    except Exception as exc:
        logger.warning("Could not load raw CSV: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Figure 1 -- price overview
# ---------------------------------------------------------------------------


def fig_price_overview(parquet_dir: Path, out_path: Path) -> None:
    """Close price line for 'extended' scope, log y, weekly down-sample."""
    df = _load_tf_scope(parquet_dir, "extended", "W1")
    if df is None or df.empty:
        df = _load_tf_scope(parquet_dir, "extended", "D1")
    if df is None or df.empty:
        logger.warning("No data for price overview; skipping.")
        return

    _apply_style()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df["ts"], df["close"], color=_COLORS["extended"], linewidth=0.8, label="Close")
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.yaxis.get_major_formatter().set_scientific(False)
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("XAUUSD Close (USD/oz, log scale)")
    ax.set_title("XAUUSD Close Price -- 2020 to 2026-05")
    ax.legend(loc="upper left")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    _add_caption(fig)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 2 -- spread before / after
# ---------------------------------------------------------------------------


def fig_spread_before_after(
    parquet_dir: Path,
    raw_csv: Path,
    out_path: Path,
) -> None:
    """Two histograms: raw spread_points vs cleaned spread_points."""
    df_clean = _load_tf_scope(parquet_dir, "extended", "M1")
    df_raw = _load_raw_m1(raw_csv)

    _apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=False)

    def _plot_hist(ax: plt.Axes, data: pd.Series, color: str, label: str) -> None:
        counts, bins, _ = ax.hist(
            data.clip(0, data.quantile(0.999)),
            bins=100,
            color=color,
            alpha=0.75,
            label=label,
            edgecolor="none",
        )
        p99 = data.quantile(0.99)
        ax.axvline(p99, color="black", linestyle="--", linewidth=1.2, label=f"p99 = {p99:.0f}")
        ax.set_yscale("log")
        ax.set_xlabel("Spread (MT5 points)")
        ax.set_ylabel("Bar count (log scale)")
        ax.legend()

    if df_raw is not None and "spread_points" in df_raw.columns:
        _plot_hist(axes[0], df_raw["spread_points"], _COLORS["raw"], "Raw data")
    else:
        axes[0].text(
            0.5,
            0.5,
            "Raw data\nnot available",
            ha="center",
            va="center",
            transform=axes[0].transAxes,
        )

    if df_clean is not None and "spread_points" in df_clean.columns:
        _plot_hist(
            axes[1], df_clean["spread_points"].astype(float), _COLORS["cleaned"], "Cleaned data"
        )
    else:
        axes[1].text(
            0.5,
            0.5,
            "Cleaned data\nnot available",
            ha="center",
            va="center",
            transform=axes[1].transAxes,
        )

    axes[0].set_title("Raw: Spread Distribution")
    axes[1].set_title("Cleaned: Spread Distribution")
    fig.suptitle("Spread (MT5 Points) Before and After Cleaning", fontsize=12)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    _add_caption(fig)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 3 -- spread_pips by hour
# ---------------------------------------------------------------------------


def fig_spread_pips_by_hour(parquet_dir: Path, out_path: Path) -> None:
    """Boxplot of spread_pips by hour of day (cleaned M1)."""
    df = _load_tf_scope(parquet_dir, "extended", "M1")
    if df is None or df.empty or "spread_pips" not in df.columns:
        logger.warning("No M1 cleaned data for spread_pips_by_hour; skipping.")
        return

    df = df.copy()
    df["hour"] = df["ts"].dt.hour
    groups = [df.loc[df["hour"] == h, "spread_pips"].dropna().values for h in range(24)]

    _apply_style()
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.boxplot(
        groups,
        positions=list(range(24)),
        widths=0.6,
        patch_artist=True,
        medianprops={"color": "black", "linewidth": 1.5},
        boxprops={"facecolor": _COLORS["cleaned"], "alpha": 0.5},
        flierprops={"marker": ".", "markersize": 2, "alpha": 0.3},
        whis=[5, 95],
    )
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45, ha="right")
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Spread (pips)")
    ax.set_title("XAUUSD Spread (pips) by Hour of Day -- Cleaned Data")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    _add_caption(fig)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 4 -- gap heatmap
# ---------------------------------------------------------------------------


def fig_gap_heatmap(parquet_dir: Path, out_path: Path) -> None:
    """Heatmap: day-of-week x hour-of-day showing 1 - bar_present_ratio."""
    df = _load_tf_scope(parquet_dir, "extended", "M1")
    if df is None or df.empty:
        logger.warning("No M1 data for gap heatmap; skipping.")
        return

    df = df.copy()
    df["dow"] = df["ts"].dt.dayofweek  # 0=Mon, 6=Sun
    df["hour"] = df["ts"].dt.hour

    # Expected minutes per cell ≈ (total weeks) * 60
    total_weeks = (df["ts"].max() - df["ts"].min()).days / 7
    expected_per_cell = max(total_weeks * 60, 1)

    pivot = df.groupby(["dow", "hour"]).size().unstack(fill_value=0)
    # Ensure all hours present
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot.reindex(columns=range(24))

    gap_ratio = 1.0 - (pivot / expected_per_cell).clip(0, 1)

    _all_dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    n_dow = gap_ratio.shape[0]
    # Reindex pivot to ensure all 7 days are present (fill missing with 1.0 = always gap)
    full_idx = pd.Index(range(7), name="dow")
    gap_ratio = gap_ratio.reindex(full_idx, fill_value=1.0)
    n_dow = gap_ratio.shape[0]
    dow_labels = _all_dow_labels[:n_dow]

    _apply_style()
    fig, ax = plt.subplots(figsize=(14, 4))
    im = ax.imshow(
        gap_ratio.values,
        aspect="auto",
        cmap="YlOrRd",
        vmin=0,
        vmax=1,
        origin="upper",
    )
    plt.colorbar(im, ax=ax, label="Gap ratio (1 = always missing)")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)])
    ax.set_yticks(range(n_dow))
    ax.set_yticklabels(dow_labels)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Day of Week")
    ax.set_title("XAUUSD M1 Gap Heatmap -- Missing Bar Ratio by Day-of-Week and Hour")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    _add_caption(fig)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 5 -- rows per timeframe
# ---------------------------------------------------------------------------


def fig_rows_per_timeframe(
    row_counts: dict[str, dict[str, int]],
    out_path: Path,
) -> None:
    """Bar chart: rows per timeframe per scope."""
    tfs = ALL_TFS
    scopes = [s for s in ALL_SCOPES if s in row_counts]
    n_scopes = len(scopes)
    if n_scopes == 0:
        logger.warning("No row counts provided; skipping rows_per_timeframe.")
        return

    x = np.arange(len(tfs))
    width = 0.35

    _apply_style()
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, scope in enumerate(scopes):
        counts = [row_counts[scope].get(tf, 0) for tf in tfs]
        offset = (i - n_scopes / 2 + 0.5) * width
        ax.bar(x + offset, counts, width, label=scope, color=_COLORS.get(scope), alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(tfs)
    ax.set_xlabel("Timeframe")
    ax.set_ylabel("Row count")
    ax.set_title("Row Counts per Timeframe and Scope")
    ax.set_yscale("log")
    ax.legend()
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    _add_caption(fig)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 6 -- flash crash
# ---------------------------------------------------------------------------


def fig_flash_crash(
    parquet_dir: Path,
    raw_csv: Path,
    out_path: Path,
) -> None:
    """Close price 2021-08-08 18:00 -> 2021-08-09 04:00 raw vs cleaned."""
    t_start = pd.Timestamp("2021-08-08 18:00", tz="UTC")
    t_end = pd.Timestamp("2021-08-09 04:00", tz="UTC")

    df_clean = _load_tf_scope(parquet_dir, "extended", "M1")
    df_raw = _load_raw_m1(raw_csv)

    def _window(df: pd.DataFrame | None) -> pd.DataFrame | None:
        if df is None or df.empty:
            return None
        ts_col = df["ts"] if "ts" in df.columns else df.index
        mask = (ts_col >= t_start) & (ts_col <= t_end)
        return df[mask]

    w_raw = _window(df_raw)
    w_clean = _window(df_clean)

    if (w_raw is None or w_raw.empty) and (w_clean is None or w_clean.empty):
        logger.warning("No data in flash-crash window; skipping.")
        return

    _apply_style()
    fig, ax = plt.subplots(figsize=(12, 4))

    if w_raw is not None and not w_raw.empty:
        ax.plot(
            w_raw["ts"], w_raw["close"], color=_COLORS["raw"], linewidth=0.8, alpha=0.7, label="Raw"
        )
    if w_clean is not None and not w_clean.empty:
        ax.plot(
            w_clean["ts"],
            w_clean["close"],
            color=_COLORS["cleaned"],
            linewidth=1.0,
            label="Cleaned",
        )

    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("XAUUSD Close (USD/oz)")
    ax.set_title("Gold Flash Crash -- 2021-08-09 (Raw vs Cleaned, M1)")
    ax.legend()
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    _add_caption(fig)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# HTML report (plotly)
# ---------------------------------------------------------------------------


def build_html_report(
    parquet_dir: Path,
    raw_csv: Path,
    row_counts: dict[str, dict[str, int]],
    out_html: Path,
) -> None:
    """Build a single-file plotly HTML report embedding interactive figures."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
        from plotly.subplots import make_subplots
    except ImportError:
        logger.warning("plotly not available; skipping HTML report.")
        return

    out_html.parent.mkdir(parents=True, exist_ok=True)
    figures_html_parts: list[str] = []

    # --- Fig 1: Price overview (extended W1) ---
    df_w1 = _load_tf_scope(parquet_dir, "extended", "W1")
    if df_w1 is None or df_w1.empty:
        df_w1 = _load_tf_scope(parquet_dir, "extended", "D1")

    if df_w1 is not None and not df_w1.empty:
        fig1 = go.Figure()
        fig1.add_trace(
            go.Scatter(
                x=df_w1["ts"],
                y=df_w1["close"],
                mode="lines",
                name="Close",
                line={"color": "#2563EB", "width": 1},
            )
        )
        fig1.update_layout(
            title="XAUUSD Close Price -- 2020 to 2026-05 (log scale)",
            xaxis_title="Date (UTC)",
            yaxis_title="Close (USD/oz)",
            yaxis_type="log",
            template="simple_white",
            height=450,
            annotations=[
                {
                    "text": DATA_SOURCE_CAPTION,
                    "xref": "paper",
                    "yref": "paper",
                    "x": 1.0,
                    "y": -0.12,
                    "showarrow": False,
                    "font": {"size": 9, "color": "gray"},
                }
            ],
        )
        figures_html_parts.append(
            "<h2>1. XAUUSD Price Overview (Weekly, Extended Scope)</h2>"
            + pio.to_html(fig1, full_html=False, include_plotlyjs=False)
        )

    # --- Fig 2: Spread before/after ---
    df_m1 = _load_tf_scope(parquet_dir, "extended", "M1")
    df_raw = _load_raw_m1(raw_csv)

    fig2 = make_subplots(rows=1, cols=2, subplot_titles=["Raw Spread", "Cleaned Spread"])
    if df_raw is not None and "spread_points" in df_raw.columns:
        sp_raw = df_raw["spread_points"].clip(0, df_raw["spread_points"].quantile(0.999))
        fig2.add_trace(
            go.Histogram(x=sp_raw, nbinsx=100, name="Raw", marker_color="#DC2626", opacity=0.75),
            row=1,
            col=1,
        )
        p99_raw = df_raw["spread_points"].quantile(0.99)
        fig2.add_vline(
            x=p99_raw,
            line_dash="dash",
            line_color="black",
            annotation_text=f"p99={p99_raw:.0f}",
            row=1,
            col=1,
        )
    if df_m1 is not None and "spread_points" in df_m1.columns:
        sp_clean = (
            df_m1["spread_points"]
            .astype(float)
            .clip(0, df_m1["spread_points"].astype(float).quantile(0.999))
        )
        fig2.add_trace(
            go.Histogram(
                x=sp_clean, nbinsx=100, name="Cleaned", marker_color="#2563EB", opacity=0.75
            ),
            row=1,
            col=2,
        )
        p99_cl = df_m1["spread_points"].astype(float).quantile(0.99)
        fig2.add_vline(
            x=p99_cl,
            line_dash="dash",
            line_color="black",
            annotation_text=f"p99={p99_cl:.0f}",
            row=1,
            col=2,
        )
    fig2.update_layout(
        title="Spread Distribution Before and After Cleaning",
        yaxis_type="log",
        yaxis2_type="log",
        template="simple_white",
        height=420,
        showlegend=True,
    )
    figures_html_parts.append(
        "<h2>2. Spread Distribution Before vs After Cleaning</h2>"
        + pio.to_html(fig2, full_html=False, include_plotlyjs=False)
    )

    # --- Fig 3: Spread pips by hour ---
    if df_m1 is not None and not df_m1.empty and "spread_pips" in df_m1.columns:
        df_h = df_m1.copy()
        df_h["hour"] = df_h["ts"].dt.hour
        fig3 = go.Figure()
        for h in range(24):
            vals = df_h.loc[df_h["hour"] == h, "spread_pips"].dropna().values
            fig3.add_trace(
                go.Box(
                    y=vals,
                    name=f"{h:02d}",
                    marker_color="#2563EB",
                    opacity=0.6,
                    showlegend=False,
                    boxpoints=False,
                )
            )
        fig3.update_layout(
            title="XAUUSD Spread (pips) by Hour of Day -- Cleaned M1",
            xaxis_title="Hour of Day (UTC)",
            yaxis_title="Spread (pips)",
            template="simple_white",
            height=430,
        )
        figures_html_parts.append(
            "<h2>3. Spread (pips) by Hour of Day</h2>"
            + pio.to_html(fig3, full_html=False, include_plotlyjs=False)
        )

    # --- Summary table ---
    table_rows = ""
    for scope in ALL_SCOPES:
        if scope not in row_counts:
            continue
        for tf in ALL_TFS:
            cnt = row_counts[scope].get(tf, "N/A")
            # Compute median spread_pips if M1 available
            med_spread = "N/A"
            if tf == "M1" and df_m1 is not None and "spread_pips" in df_m1.columns:
                med_spread = f"{df_m1['spread_pips'].median():.2f}"
            table_rows += (
                f"<tr><td>{scope}</td><td>{tf}</td><td>{cnt:,}"
                if isinstance(cnt, int)
                else f"<td>{cnt}"
            )
            table_rows += f"</td><td>{med_spread}</td></tr>\n"

    summary_table = f"""
<h2>4. Row Count Summary</h2>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;font-family:monospace;font-size:13px">
  <thead>
    <tr><th>Scope</th><th>Timeframe</th><th>Row Count</th><th>Median Spread (pips)</th></tr>
  </thead>
  <tbody>
    {table_rows}
  </tbody>
</table>
"""

    # Assemble HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>XAUUSD Time Series Data Preparation -- Report</title>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 1100px; margin: 0 auto; padding: 24px; }}
    h1 {{ border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
    h2 {{ color: #1f2937; margin-top: 40px; }}
    table {{ margin-bottom: 32px; }}
    td, th {{ padding: 6px 12px; }}
    thead tr {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>XAUUSD M1 Time Series -- Data Preparation Report</h1>
  <p style="color:#6b7280">{DATA_SOURCE_CAPTION}</p>
  {"".join(figures_html_parts)}
  {summary_table}
</body>
</html>
"""
    out_html.write_text(html_content, encoding="utf-8")
    logger.info("Saved HTML report -> %s", out_html)


# ---------------------------------------------------------------------------
# High-level driver
# ---------------------------------------------------------------------------


def run_visualize(
    cfg: Config | None = None,
    row_counts: dict[str, dict[str, int]] | None = None,
) -> None:
    """Produce all figures and the HTML report."""
    if cfg is None:
        cfg = Config()
    if row_counts is None:
        row_counts = {}

    figs_dir = cfg.figures_dir
    figs_dir.mkdir(parents=True, exist_ok=True)

    fig_price_overview(cfg.parquet_dir, figs_dir / "price_overview.png")
    fig_spread_before_after(cfg.parquet_dir, cfg.raw_csv, figs_dir / "spread_before_after.png")
    fig_spread_pips_by_hour(cfg.parquet_dir, figs_dir / "spread_pips_by_hour.png")
    fig_gap_heatmap(cfg.parquet_dir, figs_dir / "gap_heatmap.png")
    fig_rows_per_timeframe(row_counts, figs_dir / "rows_per_timeframe.png")
    fig_flash_crash(cfg.parquet_dir, cfg.raw_csv, figs_dir / "flash_crash_2021_08_09.png")
    build_html_report(
        cfg.parquet_dir,
        cfg.raw_csv,
        row_counts,
        cfg.reports_dir / "report.html",
    )
