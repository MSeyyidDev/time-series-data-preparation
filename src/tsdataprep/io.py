"""I/O helpers: read MT5 CSV, write/read Parquet, compute file SHA-256."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Dtype hints for the raw MT5 CSV read (before normalization)
_RAW_DTYPES: dict[str, str] = {
    "<DATE>": "str",
    "<TIME>": "str",
    "<OPEN>": "float64",
    "<HIGH>": "float64",
    "<LOW>": "float64",
    "<CLOSE>": "float64",
    "<TICKVOL>": "int64",
    "<VOL>": "int64",
    "<SPREAD>": "int32",
}

# PyArrow schema matching the canonical normalized schema
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("ts", pa.timestamp("ns", tz="UTC")),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("tick_volume", pa.int64()),
        pa.field("real_volume", pa.int64()),
        pa.field("spread_points", pa.int32()),
        pa.field("spread_pips", pa.float32()),
    ]
)

_CHUNK_SIZE = 1024 * 1024  # 1 MB for SHA-256 streaming


def load_raw_csv(path: str | Path) -> pd.DataFrame:
    """Read MT5 tab-separated CSV, return raw DataFrame with original column names."""
    return pd.read_csv(
        str(path),
        sep="\t",
        dtype=_RAW_DTYPES,
        engine="c",
    )


def write_parquet(df: pd.DataFrame, path: str | Path, *, row_group_size: int = 100_000) -> None:
    """Write canonical DataFrame to a Parquet file (zstd level 3, fixed row group)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False)
    pq.write_table(
        table,
        str(path),
        compression="zstd",
        compression_level=3,
        row_group_size=row_group_size,
        write_statistics=True,
    )


def read_parquet(path: str | Path) -> pd.DataFrame:
    """Read a canonical Parquet file back to a pandas DataFrame."""
    return pq.read_table(str(path), schema=PARQUET_SCHEMA).to_pandas()


def compute_file_sha256(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file by streaming 1 MB chunks."""
    h = hashlib.sha256()
    with open(str(path), "rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()
