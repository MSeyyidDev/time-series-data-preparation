"""Central configuration dataclass for tsdataprep."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen constants (spec section 3.3)
# ---------------------------------------------------------------------------

#: Aggregation spec used for all resample operations.
AGG_DICT: dict[str, str] = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "tick_volume": "sum",
    "real_volume": "sum",
    "spread_points": "mean",
    "spread_pips": "mean",
}

#: Mapping from short timeframe label -> pandas offset alias.
FREQ_MAP: dict[str, str | None] = {
    "M1": None,  # pass-through, not resampled
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
    "H4": "4h",
    "H12": "12h",
    "D1": "1D",
    "W1": "1W",
    "MN1": "1MS",
}

#: Timeframes that use year-partitioned output layout.
YEAR_PARTITIONED_TFS: list[str] = ["M1", "M5", "M15", "H1", "H4", "H12", "D1"]

#: Timeframes that use a single file (no year partition).
SINGLE_FILE_TFS: list[str] = ["W1", "MN1"]

#: All timeframes in ascending granularity order.
ALL_TFS: list[str] = ["M1", "M5", "M15", "H1", "H4", "H12", "D1", "W1", "MN1"]

#: Date scopes.
SCOPE_WINDOWS: dict[str, tuple[str, str]] = {
    "clean_5y": ("2020-01-01", "2024-12-31 23:59:59"),
    "extended": ("2020-01-01", "2026-05-08 23:59:59"),
}

ALL_SCOPES: list[str] = ["clean_5y", "extended"]

# ---------------------------------------------------------------------------
# Data citation
# ---------------------------------------------------------------------------

DATA_SOURCE_CAPTION = "Source: MetaQuotes-Demo XAUUSD M1, 2020-01 to 2026-05"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration for the tsdataprep pipeline."""

    # --- paths ---
    project_root: Path = field(default_factory=lambda: _default_project_root())
    raw_csv: Path = field(default=None)  # type: ignore[assignment]
    interim_dir: Path = field(default=None)  # type: ignore[assignment]
    processed_dir: Path = field(default=None)  # type: ignore[assignment]
    parquet_dir: Path = field(default=None)  # type: ignore[assignment]
    duckdb_file: Path = field(default=None)  # type: ignore[assignment]
    reports_dir: Path = field(default=None)  # type: ignore[assignment]
    figures_dir: Path = field(default=None)  # type: ignore[assignment]

    # --- pipeline params ---
    scopes: list[str] = field(default_factory=lambda: list(ALL_SCOPES))
    timeframes: list[str] = field(default_factory=lambda: list(ALL_TFS))
    parquet_compression: str = "zstd"
    parquet_compression_level: int = 3

    def __post_init__(self) -> None:
        root = self.project_root
        if self.raw_csv is None:
            self.raw_csv = root / "data" / "raw" / "XAUUSD_M1.csv"
        if self.interim_dir is None:
            self.interim_dir = root / "data" / "interim"
        if self.processed_dir is None:
            self.processed_dir = root / "data" / "processed"
        if self.parquet_dir is None:
            self.parquet_dir = root / "data" / "processed" / "parquet"
        if self.duckdb_file is None:
            self.duckdb_file = root / "data" / "processed" / "xauusd.duckdb"
        if self.reports_dir is None:
            self.reports_dir = root / "reports"
        if self.figures_dir is None:
            self.figures_dir = root / "reports" / "figures"

    # helpers
    def interim_parquet(self, scope: str) -> Path:
        """Return the path to the cleaned M1 Parquet file for a given scope."""
        if scope == "clean_5y":
            return self.interim_dir / "xauusd_m1_clean_5y.parquet"
        if scope == "extended":
            return self.interim_dir / "xauusd_m1_extended.parquet"
        raise ValueError(f"Unknown scope: {scope!r}")

    def parquet_tf_dir(self, scope: str, tf: str) -> Path:
        """Return the directory for a given scope + timeframe combination."""
        return self.parquet_dir / scope / tf

    def duckdb_table(self, tf: str, scope: str) -> str:
        """Return the DuckDB table name for a given timeframe + scope."""
        return f"xauusd_{tf.lower()}_{scope}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_project_root() -> Path:
    """Resolve the project root: walk up from this file until we find SHARED_SPEC.md."""
    here = Path(__file__).resolve().parent
    for candidate in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
        if (candidate / "SHARED_SPEC.md").exists():
            return candidate
    # Fallback: cwd
    return Path(os.getcwd())
