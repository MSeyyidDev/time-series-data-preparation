"""End-to-end cleaning driver: raw CSV -> clean M1 Parquet + quality report.

Usage:
    python scripts/02_clean.py \\
        --input data/raw/XAUUSD_M1.csv \\
        --out-interim data/interim \\
        --out-processed data/processed

Produces:
    data/interim/xauusd_m1_clean_5y.parquet
    data/interim/xauusd_m1_extended.parquet
    data/processed/quality_report.json
    data/processed/manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# Allow importing tsdataprep from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tsdataprep.clean import clean
from tsdataprep.io import compute_file_sha256, load_raw_csv, write_parquet
from tsdataprep.normalize import normalize
from tsdataprep.validate import validate


def _package_versions() -> dict[str, str]:
    """Collect relevant package versions for reproducibility."""
    import importlib.metadata as im
    versions: dict[str, str] = {}
    for pkg in ["pandas", "pyarrow", "numpy", "duckdb"]:
        try:
            versions[pkg] = im.version(pkg)
        except im.PackageNotFoundError:
            versions[pkg] = "not installed"
    return versions


def run(
    input_path: Path,
    out_interim: Path,
    out_processed: Path,
) -> None:
    """Run the full cleaning pipeline for both scopes."""
    out_interim.mkdir(parents=True, exist_ok=True)
    out_processed.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] Computing SHA-256 for {input_path.name} ...", flush=True)
    sha256 = compute_file_sha256(input_path)
    print(f"      sha256={sha256[:16]}...", flush=True)

    print(f"[2/6] Loading raw CSV ({input_path.stat().st_size / 1e6:.1f} MB) ...", flush=True)
    raw_df = load_raw_csv(input_path)
    input_rows = len(raw_df)
    print(f"      {input_rows:,} rows loaded", flush=True)

    print("[3/6] Normalizing (UTC ts, column rename, dtypes) ...", flush=True)
    norm_df = normalize(raw_df)
    print(f"      {len(norm_df):,} rows after normalization", flush=True)

    scopes_out: dict[str, dict] = {}
    clean_dfs: dict[str, pd.DataFrame] = {}

    for scope in ("clean_5y", "extended"):
        print(f"[4/6] Cleaning scope={scope!r} ...", flush=True)
        clean_df, counts = clean(norm_df.copy(), scope=scope)  # type: ignore[arg-type]
        clean_dfs[scope] = clean_df

        print(f"[5/6] Validating scope={scope!r} ...", flush=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            report_entry = validate(clean_df, scope=scope)
        for w in caught:
            print(f"      WARNING: {w.message}", flush=True)

        output_path = out_interim / f"xauusd_m1_{scope}.parquet"
        print(f"[6/6] Writing {output_path.name} ...", flush=True)
        write_parquet(clean_df, output_path)
        file_size_mb = output_path.stat().st_size / 1e6

        scopes_out[scope] = {
            "output_rows": len(clean_df),
            "dropped_by_reason": counts,
            "median_spread_pips": report_entry["median_spread_pips"],
            "mean_spread_pips": report_entry["mean_spread_pips"],
            "date_range": report_entry["date_range"],
            "parquet_path": str(output_path),
            "parquet_size_mb": round(file_size_mb, 2),
        }
        total_dropped = sum(counts.values())
        print(
            f"      {len(clean_df):,} rows kept, {total_dropped:,} dropped, "
            f"median_spread_pips={report_entry['median_spread_pips']:.3f}",
            flush=True,
        )

    # Write quality_report.json
    quality_report = {
        "input_file": str(input_path),
        "input_sha256": sha256,
        "input_rows": input_rows,
        "scopes": scopes_out,
        "params": {
            "spread_outlier_method": "per_year_p99",
            "return_explosion_threshold": "8*MAD(ret)",
            "return_explosion_spread_condition": "spread > p95",
            "mad_scale_factor": 1.4826,
            "broker_time_assumption": "UTC (no shift applied -- see normalize.py docstring)",
        },
        "package_versions": _package_versions(),
        "generated_at": datetime.now(UTC).isoformat(),
    }

    qr_path = out_processed / "quality_report.json"
    with open(qr_path, "w", encoding="utf-8") as fh:
        json.dump(quality_report, fh, indent=2)
    print(f"\nQuality report -> {qr_path}", flush=True)

    # Write manifest.json (subset of quality_report)
    manifest = {
        "input_file": str(input_path),
        "input_sha256": sha256,
        "input_rows": input_rows,
        "clean_5y_rows": scopes_out["clean_5y"]["output_rows"],
        "extended_rows": scopes_out["extended"]["output_rows"],
        "clean_5y_parquet": scopes_out["clean_5y"]["parquet_path"],
        "extended_parquet": scopes_out["extended"]["parquet_path"],
        "generated_at": quality_report["generated_at"],
    }
    manifest_path = out_processed / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Manifest        -> {manifest_path}", flush=True)

    # Summary
    print("\n--- Summary ---")
    for scope, info in scopes_out.items():
        print(f"  {scope}: {info['output_rows']:,} rows, "
              f"median_spread_pips={info['median_spread_pips']:.3f}, "
              f"size={info['parquet_size_mb']} MB")
        for reason, cnt in info["dropped_by_reason"].items():
            if cnt:
                print(f"    dropped[{reason}]={cnt:,}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Clean XAUUSD M1 data")
    parser.add_argument("--input", required=True, help="Path to raw CSV")
    parser.add_argument("--out-interim", default="data/interim", help="Interim Parquet directory")
    parser.add_argument("--out-processed", default="data/processed", help="Processed JSON directory")
    args = parser.parse_args()

    run(
        input_path=Path(args.input),
        out_interim=Path(args.out_interim),
        out_processed=Path(args.out_processed),
    )


if __name__ == "__main__":
    main()
