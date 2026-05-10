"""tsdataprep -- XAUUSD M1 Time Series Data Preparation package."""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "tsdataprep contributors"
__all__ = [
    "__version__",
    "Config",
    "resample_m1",
    "run_resample",
    "write_duckdb",
    "run_visualize",
]

from .config import Config
from .resample import resample_m1, run_resample, write_duckdb
from .visualize import run_visualize
