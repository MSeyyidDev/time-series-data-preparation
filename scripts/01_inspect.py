"""Quick profile of the raw MT5 XAUUSD M1 CSV.

Usage:
    python scripts/01_inspect.py --input data/raw/XAUUSD_M1.csv

Prints a markdown summary table used in docs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Allow importing tsdataprep from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tsdataprep.io import load_raw_csv


def _gap_distribution(ts: pd.Series) -> dict[str, int]:
    """Return count of gaps by bucket (minutes)."""
    diffs_min = ts.diff().dt.total_seconds().dropna() / 60
    return {
        "gaps_1m": int((diffs_min == 1).sum()),
        "gaps_2_60m": int(((diffs_min > 1) & (diffs_min <= 60)).sum()),
        "gaps_1h_2h": int(((diffs_min > 60) & (diffs_min <= 120)).sum()),
        "gaps_gt2h": int((diffs_min > 120).sum()),
    }


def inspect(input_path: str) -> None:
    """Load raw CSV and print a markdown profile."""
    path = Path(input_path)
    print(f"## Raw Data Profile: `{path.name}`\n")

    df = load_raw_csv(path)
    n_rows = len(df)

    # Build ts for gap analysis
    ts = pd.to_datetime(
        df["<DATE>"].astype(str) + " " + df["<TIME>"].astype(str),
        format="%Y.%m.%d %H:%M:%S",
    )

    spread = df["<SPREAD>"]
    ret = df["<CLOSE>"].pct_change().dropna()

    print("| Metric | Value |")
    print("|---|---|")
    print(f"| Row count | {n_rows:,} |")
    print(f"| Date range start | {ts.min()} |")
    print(f"| Date range end | {ts.max()} |")
    print(f"| Spread mean | {spread.mean():.2f} pts |")
    print(f"| Spread median | {spread.median():.0f} pts |")
    print(f"| Spread p99 | {spread.quantile(0.99):.0f} pts |")
    print(f"| Spread max | {spread.max():.0f} pts |")
    print(
        f"| OHLC-invalid bars | {int(((df['<HIGH>'] < df['<LOW>']) | (df['<OPEN>'] <= 0)).sum())} |"
    )

    gaps = _gap_distribution(ts)
    print(f"| Inter-bar gaps == 1 min | {gaps['gaps_1m']:,} |")
    print(f"| Inter-bar gaps 2-60 min | {gaps['gaps_2_60m']:,} |")
    print(f"| Inter-bar gaps 1h-2h | {gaps['gaps_1h_2h']:,} |")
    print(f"| Inter-bar gaps > 2h | {gaps['gaps_gt2h']:,} |")

    print("\n### Top 10 Bars by Absolute Return\n")
    print("| ts | |ret| (%) | spread_pts | close |")
    print("|---|---|---|---|")
    top_idx = ret.abs().nlargest(10).index
    for idx in top_idx:
        print(
            f"| {ts.iloc[idx]} | {abs(ret.iloc[idx]) * 100:.4f}% "
            f"| {spread.iloc[idx]} | {df['<CLOSE>'].iloc[idx]:.2f} |"
        )


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Inspect raw MT5 CSV")
    parser.add_argument("--input", required=True, help="Path to raw CSV")
    args = parser.parse_args()
    inspect(args.input)


if __name__ == "__main__":
    main()
