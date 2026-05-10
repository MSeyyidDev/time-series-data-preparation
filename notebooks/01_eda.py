# %% [markdown]
# # XAUUSD M1 -- Exploratory Data Analysis
#
# Demonstrates loading from DuckDB, basic OHLC plot, and spread histogram.
# Run as a script: `python notebooks/01_eda.py`
# Or open in VS Code / Jupyter with Jupytext.

# %%
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when running directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import duckdb  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")  # change to "TkAgg" or "Qt5Agg" for interactive display
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from tsdataprep.config import Config  # noqa: E402

# %% [markdown]
# ## Configuration

# %%
cfg = Config()
db_path = cfg.duckdb_file
print(f"DuckDB path: {db_path}")
print(f"Exists: {db_path.exists()}")

# %% [markdown]
# ## List available tables

# %%
if db_path.exists():
    con = duckdb.connect(str(db_path), read_only=True)
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    print(f"Tables ({len(tables)}):")
    for t in tables:
        cnt = con.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
        print(f"  {t[0]}: {cnt:,} rows")
    con.close()
else:
    print("DuckDB file not found. Run scripts/03_resample.py first.")

# %% [markdown]
# ## Load H1 data (extended scope)

# %%
df_h1 = None
if db_path.exists():
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df_h1 = con.execute(
            "SELECT * FROM xauusd_h1_extended ORDER BY ts"
        ).df()
        df_h1["ts"] = pd.to_datetime(df_h1["ts"], utc=True)
        print(f"H1 extended: {len(df_h1):,} rows")
        print(df_h1.dtypes)
        print(df_h1.head(3))
    except Exception as e:
        print(f"Could not load H1: {e}")
    finally:
        con.close()

# %% [markdown]
# ## OHLC overview -- close price

# %%
fig, ax = plt.subplots(figsize=(14, 5))
if df_h1 is not None and not df_h1.empty:
    ax.plot(df_h1["ts"], df_h1["close"], color="#2563EB", linewidth=0.7, label="H1 Close")
    ax.set_xlabel("Date (UTC)")
    ax.set_ylabel("XAUUSD (USD/oz)")
    ax.set_title("XAUUSD H1 Close Price -- Extended Scope")
    ax.legend()
    ax.grid(True, alpha=0.3)
else:
    ax.text(0.5, 0.5, "No H1 data available.\nRun scripts/03_resample.py first.",
            ha="center", va="center", transform=ax.transAxes, fontsize=12)

fig.tight_layout()
out_path = _ROOT / "reports" / "figures" / "eda_close_price.png"
out_path.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out_path, dpi=120, bbox_inches="tight")
print(f"Saved: {out_path}")
plt.close(fig)

# %% [markdown]
# ## Spread histogram (M1 cleaned)

# %%
df_m1 = None
if db_path.exists():
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df_m1 = con.execute(
            "SELECT spread_pips FROM xauusd_m1_extended"
        ).df()
        print(f"M1 extended rows: {len(df_m1):,}")
    except Exception as e:
        print(f"Could not load M1: {e}")
    finally:
        con.close()

fig, ax = plt.subplots(figsize=(10, 4))
if df_m1 is not None and not df_m1.empty and "spread_pips" in df_m1.columns:
    clipped = df_m1["spread_pips"].clip(0, df_m1["spread_pips"].quantile(0.999))
    ax.hist(clipped, bins=80, color="#2563EB", alpha=0.75, edgecolor="none")
    median_sp = df_m1["spread_pips"].median()
    ax.axvline(median_sp, color="black", linestyle="--", label=f"Median = {median_sp:.2f} pips")
    ax.set_xlabel("Spread (pips)")
    ax.set_ylabel("Count")
    ax.set_title("XAUUSD Spread Distribution -- Cleaned M1 Extended")
    ax.legend()
    ax.grid(True, alpha=0.3)
    print(f"Spread median: {median_sp:.2f} pips")
else:
    ax.text(0.5, 0.5, "No M1 data available.", ha="center", va="center",
            transform=ax.transAxes)

fig.tight_layout()
out_spread = _ROOT / "reports" / "figures" / "eda_spread_hist.png"
fig.savefig(out_spread, dpi=120, bbox_inches="tight")
print(f"Saved: {out_spread}")
plt.close(fig)

# %% [markdown]
# ## Row count summary

# %%
if db_path.exists():
    con = duckdb.connect(str(db_path), read_only=True)
    rows_data = []
    for t_row in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' "
        "ORDER BY table_name"
    ).fetchall():
        tname = t_row[0]
        cnt = con.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        rows_data.append({"table": tname, "rows": cnt})
    con.close()

    summary_df = pd.DataFrame(rows_data)
    print("\nRow count summary:")
    print(summary_df.to_string(index=False))
else:
    print("DuckDB not available.")

# %%
print("EDA notebook complete.")
