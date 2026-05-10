"""Resample cleaned M1 data to all required timeframes.

Reads Hive-partitioned or flat Parquet from `data/interim/`, writes:
  - Hive-partitioned Parquet under `data/processed/parquet/{scope}/{tf}/`
  - A DuckDB file `data/processed/xauusd.duckdb` with one table per tf+scope.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import (
    AGG_DICT,
    ALL_SCOPES,
    ALL_TFS,
    FREQ_MAP,
    YEAR_PARTITIONED_TFS,
    Config,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_ARROW_SCHEMA = pa.schema(
    [
        pa.field("ts", pa.timestamp("ns", tz="UTC")),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("tick_volume", pa.int64()),
        pa.field("real_volume", pa.int64()),
        pa.field("spread_points", pa.float32()),
        pa.field("spread_pips", pa.float32()),
    ]
)

_WRITE_ROW_GROUP_SIZE = 100_000  # deterministic row-group size


def _cast_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure correct dtypes before writing to Parquet."""
    df = df.copy()
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype("float64")
    for col in ("tick_volume", "real_volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    for col in ("spread_points", "spread_pips"):
        df[col] = df[col].astype("float32")
    return df


# ---------------------------------------------------------------------------
# Core resample function
# ---------------------------------------------------------------------------


def resample_m1(df_m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample a cleaned M1 DataFrame to the given timeframe.

    Parameters
    ----------
    df_m1:
        Must have a UTC DatetimeTZDtype index named 'ts' (or 'ts' as a column).
    tf:
        One of the keys in FREQ_MAP (e.g. 'M5', 'H1', 'D1', ...).
        'M1' is a pass-through.

    Returns
    -------
    Resampled DataFrame with 'ts' column (not index), sorted ascending, empty
    bars dropped.
    """
    if "ts" in df_m1.columns:
        df_m1 = df_m1.set_index("ts")
    if not isinstance(df_m1.index, pd.DatetimeIndex):
        raise TypeError("Expected DatetimeIndex after setting 'ts' as index.")
    if df_m1.index.tz is None:
        df_m1.index = df_m1.index.tz_localize("UTC")

    if tf == "M1":
        out = df_m1.copy()
        out.index.name = "ts"
        return out.reset_index().sort_values("ts").reset_index(drop=True)

    freq = FREQ_MAP[tf]
    if freq is None:
        raise ValueError(f"No frequency defined for timeframe {tf!r}")

    resampled = df_m1.resample(freq, label="left", closed="left").agg(AGG_DICT).dropna(how="all")
    # Drop empty bars: rows where all OHLC are NaN after dropna(how='all')
    # (dropna already handles it, but be explicit with open).
    resampled = resampled.dropna(subset=["open"])
    resampled.index.name = "ts"
    result = resampled.reset_index().sort_values("ts").reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def _write_parquet(
    df: pd.DataFrame,
    out_dir: Path,
    tf: str,
    compression: str = "zstd",
    compression_level: int = 3,
) -> None:
    """Write a DataFrame to Parquet, year-partitioned for M1..D1, flat for W1/MN1."""
    out_dir.mkdir(parents=True, exist_ok=True)
    table = _df_to_arrow(df)

    if tf in YEAR_PARTITIONED_TFS:
        # Group by year
        ts_col = df["ts"] if "ts" in df.columns else df.index
        if not hasattr(ts_col, "dt"):
            ts_col = pd.Series(ts_col)
        years = ts_col.dt.year.unique()
        for year in sorted(years):
            mask = df["ts"].dt.year == year if "ts" in df.columns else df.index.year == year
            year_dir = out_dir / f"year={year}"
            year_dir.mkdir(parents=True, exist_ok=True)
            part_path = year_dir / "part-0.parquet"
            sub_df = df[mask].copy()
            sub_table = _df_to_arrow(sub_df)
            pq.write_table(
                sub_table,
                part_path,
                compression=compression,
                compression_level=compression_level,
                row_group_size=_WRITE_ROW_GROUP_SIZE,
            )
    else:
        # Single flat file
        part_path = out_dir / "part-0.parquet"
        pq.write_table(
            table,
            part_path,
            compression=compression,
            compression_level=compression_level,
            row_group_size=_WRITE_ROW_GROUP_SIZE,
        )

    logger.debug("Wrote Parquet to %s", out_dir)


def _df_to_arrow(df: pd.DataFrame) -> pa.Table:
    """Convert DataFrame to Arrow table with canonical schema."""
    df = _cast_dtypes(df)
    # Ensure ts is included as column
    if "ts" not in df.columns and df.index.name == "ts":
        df = df.reset_index()
    # Cast ts to timestamp[ns, UTC]
    if "ts" in df.columns:
        if df["ts"].dtype == object:
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
        elif hasattr(df["ts"], "dt") and df["ts"].dt.tz is None:
            df["ts"] = df["ts"].dt.tz_localize("UTC")
    # Build arrow table using only columns in schema
    schema_names = [f.name for f in _ARROW_SCHEMA]
    cols_present = [c for c in schema_names if c in df.columns]
    return pa.Table.from_pandas(df[cols_present], preserve_index=False)


# ---------------------------------------------------------------------------
# DuckDB writer
# ---------------------------------------------------------------------------


def write_duckdb(
    parquet_dir: Path,
    duckdb_path: Path,
    scopes: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> list[str]:
    """Read all Parquet files and materialise them as DuckDB tables.

    Table names follow the spec: ``xauusd_{tf_lower}_{scope}``.

    Returns a list of created table names.
    """
    if scopes is None:
        scopes = ALL_SCOPES
    if timeframes is None:
        timeframes = ALL_TFS

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    con = duckdb.connect(str(duckdb_path))
    try:
        for scope in scopes:
            for tf in timeframes:
                tf_dir = parquet_dir / scope / tf
                if not tf_dir.exists():
                    logger.warning("Parquet dir not found, skipping: %s", tf_dir)
                    continue

                table_name = f"xauusd_{tf.lower()}_{scope}"
                con.execute(f"DROP TABLE IF EXISTS {table_name}")

                # Use read_parquet with hive_partitioning for year-partitioned tfs
                if tf in YEAR_PARTITIONED_TFS:
                    glob_path = str(tf_dir).replace("\\", "/") + "/**/*.parquet"
                    sql = (
                        f"CREATE TABLE {table_name} AS "
                        f"SELECT * FROM read_parquet('{glob_path}', "
                        f"hive_partitioning=false)"
                    )
                else:
                    glob_path = str(tf_dir).replace("\\", "/") + "/*.parquet"
                    sql = f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{glob_path}')"

                try:
                    con.execute(sql)
                    count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    logger.info("DuckDB table %s: %d rows", table_name, count)
                    created.append(table_name)
                except Exception as exc:
                    logger.error("Failed to create table %s: %s", table_name, exc)

    finally:
        con.close()

    return created


# ---------------------------------------------------------------------------
# High-level driver
# ---------------------------------------------------------------------------


def run_resample(
    cfg: Config | None = None,
    scopes: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """Run the full resample pipeline for all scopes and timeframes.

    Returns a nested dict: ``{scope: {tf: row_count}}``.
    """
    if cfg is None:
        cfg = Config()
    if scopes is None:
        scopes = cfg.scopes
    if timeframes is None:
        timeframes = cfg.timeframes

    row_counts: dict[str, dict[str, int]] = {s: {} for s in scopes}

    for scope in scopes:
        interim_path = cfg.interim_parquet(scope)
        if not interim_path.exists():
            logger.warning(
                "Interim Parquet not found for scope %r: %s -- skipping.", scope, interim_path
            )
            continue

        logger.info("Loading M1 data for scope %r from %s", scope, interim_path)
        df_m1 = pd.read_parquet(interim_path)

        # Ensure ts column present and UTC
        if "ts" not in df_m1.columns and df_m1.index.name == "ts":
            df_m1 = df_m1.reset_index()
        if "ts" in df_m1.columns:
            df_m1["ts"] = pd.to_datetime(df_m1["ts"], utc=True)

        for tf in timeframes:
            logger.info("  Resampling %s -> %s ...", scope, tf)
            try:
                df_tf = resample_m1(df_m1.copy(), tf)
                out_dir = cfg.parquet_tf_dir(scope, tf)
                _write_parquet(
                    df_tf,
                    out_dir,
                    tf,
                    compression=cfg.parquet_compression,
                    compression_level=cfg.parquet_compression_level,
                )
                row_counts[scope][tf] = len(df_tf)
                logger.info("    -> %d rows", len(df_tf))
            except Exception as exc:
                logger.error("  Failed %s/%s: %s", scope, tf, exc)
                row_counts[scope][tf] = -1

    # Build DuckDB
    logger.info("Writing DuckDB -> %s", cfg.duckdb_file)
    write_duckdb(cfg.parquet_dir, cfg.duckdb_file, scopes=scopes, timeframes=timeframes)

    return row_counts
