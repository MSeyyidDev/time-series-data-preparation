"""
Shared pytest fixtures for the Time Series Data Preparation test suite.

Do NOT add test functions here -- only fixtures used across multiple test modules.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Constants that mirror the canonical schema (spec §3.1)
# ---------------------------------------------------------------------------

CANONICAL_COLUMNS = [
    "ts",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "real_volume",
    "spread_points",
    "spread_pips",
]

CANONICAL_DTYPES: dict[str, str] = {
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "tick_volume": "int64",
    "real_volume": "int64",
    "spread_points": "int32",
    "spread_pips": "float32",
}


# ---------------------------------------------------------------------------
# Core fixture: deterministic 10k-row synthetic M1 DataFrame
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def synthetic_m1_df() -> pd.DataFrame:
    """Return a deterministic 10 000-row synthetic XAUUSD M1 DataFrame.

    The DataFrame matches the canonical schema (spec §3.1):
    - ts:            DatetimeTZDtype(tz=UTC), monotonically increasing, 1-min steps
    - open/high/low/close: float64, plausible gold prices ~1800–2000 USD
    - tick_volume:   int64, positive
    - real_volume:   int64, 0 (typical for CFD)
    - spread_points: int32, typical range 15–30 (no outliers)
    - spread_pips:   float32 = spread_points / 10

    The random walk is seeded at 42 for byte-for-byte reproducibility.
    """
    rng = np.random.default_rng(42)
    n = 10_000

    # --- timestamps: start 2020-01-02 10:00 UTC, 1-minute increments ---
    start = pd.Timestamp("2020-01-02 08:00:00", tz="UTC")  # broker 10:00 EET = 08:00 UTC
    ts = pd.date_range(start=start, periods=n, freq="1min", tz="UTC")

    # --- random-walk close price around $1,850 ---
    steps = rng.normal(loc=0.0, scale=0.15, size=n)
    close = np.cumsum(steps) + 1850.0
    close = np.clip(close, 1600.0, 2100.0)

    # --- OHLC: simulate realistic bar shape ---
    noise = rng.uniform(0.01, 0.50, size=n)
    high = close + noise
    low = close - noise
    # open is yesterday's close (shift by 1, fill first with close[0])
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    # make sure open is within [low, high]
    open_ = np.clip(open_, low, high)

    # --- volumes ---
    tick_volume = rng.integers(50, 800, size=n, dtype=np.int64)
    real_volume = np.zeros(n, dtype=np.int64)

    # --- spread: typical 15–30 points for liquid hours ---
    spread_points = rng.integers(15, 31, size=n, dtype=np.int32)
    spread_pips = (spread_points / 10.0).astype(np.float32)

    df = pd.DataFrame(
        {
            "ts": ts,
            "open": open_.astype(np.float64),
            "high": high.astype(np.float64),
            "low": low.astype(np.float64),
            "close": close.astype(np.float64),
            "tick_volume": tick_volume,
            "real_volume": real_volume,
            "spread_points": spread_points,
            "spread_pips": spread_pips,
        }
    )
    df = df.set_index("ts")
    return df


# ---------------------------------------------------------------------------
# Fixture: temporary data directory (unique per test)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """Return a temporary directory pre-populated with the expected sub-folders.

    Layout mirrors the project's data/ structure:
        <tmp>/raw/
        <tmp>/interim/
        <tmp>/processed/
    """
    for sub in ("raw", "interim", "processed"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Fixture: path to the committed sample CSV fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_csv_path() -> Path:
    """Return the absolute path to tests/fixtures/sample_m1.csv."""
    here = Path(__file__).parent
    p = here / "fixtures" / "sample_m1.csv"
    if not p.exists():
        pytest.skip(f"Sample fixture not found: {p}")
    return p
