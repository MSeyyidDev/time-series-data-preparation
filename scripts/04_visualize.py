"""Script 04 -- Generate all figures and HTML report.

Usage:
    python scripts/04_visualize.py [--parquet DIR] [--out DIR]

Reads processed Parquet from data/processed/parquet/ and raw CSV from
data/raw/XAUUSD_M1.csv. Writes PNGs to reports/figures/ and the HTML
report to reports/report.html.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("04_visualize")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from tsdataprep.config import ALL_SCOPES, ALL_TFS, Config  # noqa: E402
from tsdataprep.visualize import run_visualize  # noqa: E402


def _collect_row_counts(cfg: Config) -> dict:
    """Walk the Parquet tree and count rows per scope/tf."""
    import pyarrow.parquet as pq

    row_counts: dict[str, dict[str, int]] = {}
    for scope in ALL_SCOPES:
        row_counts[scope] = {}
        for tf in ALL_TFS:
            tf_dir = cfg.parquet_tf_dir(scope, tf)
            if not tf_dir.exists():
                continue
            try:
                ds = pq.read_table(str(tf_dir))
                row_counts[scope][tf] = len(ds)
            except Exception as exc:
                logger.warning("Could not count rows for %s/%s: %s", scope, tf, exc)
    return row_counts


def main(parquet_dir: Path | None = None, out_dir: Path | None = None) -> None:
    cfg = Config()
    if parquet_dir:
        cfg.parquet_dir = parquet_dir
    if out_dir:
        cfg.reports_dir = out_dir
        cfg.figures_dir = out_dir / "figures"

    if not cfg.parquet_dir.exists():
        logger.error("Parquet directory not found: %s", cfg.parquet_dir)
        logger.error("Run scripts/03_resample.py first.")
        sys.exit(1)

    row_counts = _collect_row_counts(cfg)
    run_visualize(cfg, row_counts)

    # Report what was produced
    figures = list(cfg.figures_dir.glob("*.png"))
    html_report = cfg.reports_dir / "report.html"
    logger.info("=" * 60)
    logger.info("Figures produced (%d):", len(figures))
    for f in sorted(figures):
        logger.info("  %s  (%.1f KB)", f.name, f.stat().st_size / 1024)
    if html_report.exists():
        logger.info(
            "HTML report: %s  (%.1f KB)",
            html_report,
            html_report.stat().st_size / 1024,
        )
    else:
        logger.warning("HTML report was NOT produced.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate figures and HTML report.")
    parser.add_argument("--parquet", type=Path, default=None,
                        help="Parquet base directory (default: data/processed/parquet/)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Report output directory (default: reports/)")
    args = parser.parse_args()
    main(parquet_dir=args.parquet, out_dir=args.out)
