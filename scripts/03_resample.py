"""Script 03 -- Resample cleaned M1 Parquet to all timeframes.

Usage:
    python scripts/03_resample.py [--interim DIR] [--out DIR]

Reads:
    data/interim/xauusd_m1_clean_5y.parquet
    data/interim/xauusd_m1_extended.parquet

Writes:
    data/processed/parquet/{scope}/{tf}/year=YYYY/part-0.parquet  (M1..D1)
    data/processed/parquet/{scope}/{tf}/part-0.parquet             (W1, MN1)
    data/processed/xauusd.duckdb
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("03_resample")

# Resolve project root and add src/ to path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from tsdataprep.config import ALL_SCOPES, ALL_TFS, Config  # noqa: E402
from tsdataprep.resample import run_resample  # noqa: E402


def _wait_for_interim(cfg: Config, timeout: int = 180, interval: int = 10) -> bool:
    """Poll until at least one interim Parquet exists (backoff up to `timeout` s)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = [s for s in ALL_SCOPES if cfg.interim_parquet(s).exists()]
        if found:
            logger.info("Interim Parquet available for scopes: %s", found)
            return True
        logger.info(
            "Waiting for interim Parquet... (%.0f s remaining)",
            deadline - time.time(),
        )
        time.sleep(interval)
    return False


def main(interim_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    cfg = Config()
    if interim_dir:
        cfg.interim_dir = interim_dir
    if out_dir:
        cfg.processed_dir = out_dir
        cfg.parquet_dir = out_dir / "parquet"
        cfg.duckdb_file = out_dir / "xauusd.duckdb"

    # Wait up to 3 min for the clean step output.
    available = [s for s in ALL_SCOPES if cfg.interim_parquet(s).exists()]
    if not available:
        logger.warning("No interim Parquet found; waiting up to 3 minutes...")
        if not _wait_for_interim(cfg, timeout=180, interval=10):
            logger.error(
                "Interim Parquet still missing after timeout. Run scripts/02_clean.py first."
            )
            sys.exit(1)

    # Run resample
    t0 = time.perf_counter()
    row_counts = run_resample(cfg)
    elapsed = time.perf_counter() - t0

    # Report
    logger.info("=" * 60)
    logger.info("Resample complete in %.1f s", elapsed)
    for scope, tfs in row_counts.items():
        logger.info("  Scope: %s", scope)
        prev = None
        for tf in ALL_TFS:
            cnt = tfs.get(tf, "MISSING")
            logger.info("    %s -> %s rows", tf, f"{cnt:,}" if isinstance(cnt, int) else cnt)
            # Sanity: monotonically decreasing
            if isinstance(cnt, int) and isinstance(prev, int) and cnt > prev:
                logger.warning(
                    "    [WARNING] %s (%d) > previous (%d) -- unexpected!", tf, cnt, prev
                )
            if isinstance(cnt, int):
                prev = cnt

    # DuckDB verification
    import duckdb as _ddb

    con = _ddb.connect(str(cfg.duckdb_file), read_only=True)
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    logger.info("DuckDB tables (%d): %s", len(tables), [t[0] for t in tables])
    con.close()

    duckdb_size_mb = cfg.duckdb_file.stat().st_size / 1_048_576 if cfg.duckdb_file.exists() else 0
    logger.info("DuckDB size: %.2f MB", duckdb_size_mb)

    return row_counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resample M1 Parquet to all timeframes.")
    parser.add_argument(
        "--interim", type=Path, default=None, help="Interim directory (default: data/interim/)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Processed output directory (default: data/processed/)",
    )
    args = parser.parse_args()
    main(interim_dir=args.interim, out_dir=args.out)
