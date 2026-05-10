"""CLI for tsdataprep (Typer-based, frozen contract from SHARED_SPEC section 7)."""
# ruff: noqa: B008  -- typer.Option() in function defaults is the canonical Typer pattern

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import ALL_SCOPES, Config
from .resample import run_resample, write_duckdb
from .visualize import run_visualize

app = typer.Typer(
    name="tsdataprep",
    help="XAUUSD M1 Time Series Data Preparation pipeline.",
    add_completion=False,
)
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tsdataprep.cli")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scope_list(scope: str) -> list[str]:
    if scope == "both":
        return list(ALL_SCOPES)
    if scope in ALL_SCOPES:
        return [scope]
    raise typer.BadParameter(
        f"scope must be one of: {', '.join(ALL_SCOPES)} or 'both'. Got: {scope!r}"
    )


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

@app.command("inspect")
def cmd_inspect(
    input: Path = typer.Option(..., "--input", help="Path to raw M1 CSV file."),
) -> None:
    """Print quick statistics on a raw MT5 XAUUSD M1 CSV file."""
    try:
        import pandas as pd
    except ImportError as exc:
        console.print("[red]pandas is required for inspect[/red]")
        raise typer.Exit(1) from exc

    if not input.exists():
        console.print(f"[red]File not found: {input}[/red]")
        raise typer.Exit(1)

    # Try to import from Agent 1's module if available, else fallback
    try:
        from tsdataprep.io import read_raw_csv  # Agent 1
        df = read_raw_csv(input)
    except ImportError:
        # Agent 1 not yet written; do basic inspection ourselves
        df = pd.read_csv(
            input,
            sep="\t",
            header=0,
        )

    console.print(f"\n[bold]File:[/bold] {input}")
    console.print(f"[bold]Rows:[/bold] {len(df):,}")
    console.print(f"[bold]Columns:[/bold] {list(df.columns)}")
    if len(df) > 0:
        console.print(f"[bold]First row:[/bold] {df.iloc[0].to_dict()}")
        console.print(f"[bold]Last row:[/bold]  {df.iloc[-1].to_dict()}")
        if "spread_points" in df.columns or "<SPREAD>" in df.columns:
            scol = "spread_points" if "spread_points" in df.columns else "<SPREAD>"
            s = df[scol].astype(float)
            console.print(
                f"[bold]Spread stats:[/bold] "
                f"min={s.min():.0f}, p50={s.median():.0f}, "
                f"p99={s.quantile(0.99):.0f}, max={s.max():.0f}"
            )


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------

@app.command("clean")
def cmd_clean(
    input: Path = typer.Option(..., "--input", help="Path to raw M1 CSV file."),
    out: Path = typer.Option(..., "--out", help="Output directory for cleaned Parquet."),
    scope: str = typer.Option("both", "--scope", help="clean_5y | extended | both"),
) -> None:
    """Clean raw M1 CSV -> cleaned Parquet (M1) per scope."""
    scopes = _scope_list(scope)
    out.mkdir(parents=True, exist_ok=True)

    try:
        # Try to import Agent 1's clean script logic
        import importlib.util
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        script_path = project_root / "scripts" / "02_clean.py"
        if script_path.exists():
            spec = importlib.util.spec_from_file_location("script_clean", script_path)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if hasattr(mod, "main"):
                mod.main(input_path=input, out_dir=out, scopes=scopes)
                return
        # Fallback: call Agent 1 module if importable
        from tsdataprep.clean import clean_pipeline  # Agent 1  # type: ignore[import]
        for s in scopes:
            clean_pipeline(input, out, scope=s)
    except (ImportError, ModuleNotFoundError) as exc:
        console.print(
            "[yellow]Agent 1 clean module not available. "
            "Run scripts/02_clean.py directly.[/yellow]"
        )
        raise typer.Exit(1) from exc

    console.print(f"[green]Clean done -> {out}[/green]")


# ---------------------------------------------------------------------------
# resample
# ---------------------------------------------------------------------------

@app.command("resample")
def cmd_resample(
    input: Path = typer.Option(
        ..., "--input",
        help="Directory containing cleaned M1 Parquet (data/interim/).",
    ),
    out: Path = typer.Option(
        ..., "--out",
        help="Output base directory (data/processed/).",
    ),
) -> None:
    """Resample cleaned M1 Parquet -> all timeframe Parquet files."""
    if not input.exists():
        console.print(f"[red]Input directory not found: {input}[/red]")
        raise typer.Exit(1)

    cfg = Config()
    cfg.interim_dir = input
    cfg.processed_dir = out
    cfg.parquet_dir = out / "parquet"
    cfg.duckdb_file = out / "xauusd.duckdb"

    console.print(f"[bold]Resampling...[/bold] interim={input} -> parquet={cfg.parquet_dir}")
    row_counts = run_resample(cfg)

    # Print summary table
    t = Table(title="Row Counts per Timeframe")
    t.add_column("Scope")
    t.add_column("TF")
    t.add_column("Rows", justify="right")
    for scope, tfs in row_counts.items():
        for tf, cnt in tfs.items():
            t.add_row(scope, tf, f"{cnt:,}" if cnt >= 0 else "FAILED")
    console.print(t)
    console.print(f"[green]Resample done -> {cfg.parquet_dir}[/green]")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@app.command("export")
def cmd_export(
    parquet: Path = typer.Option(..., "--parquet", help="Parquet base directory."),
    duckdb: Path = typer.Option(..., "--duckdb", help="Output DuckDB file path."),
) -> None:
    """Export Parquet tree -> DuckDB file."""
    if not parquet.exists():
        console.print(f"[red]Parquet directory not found: {parquet}[/red]")
        raise typer.Exit(1)

    duckdb.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold]Building DuckDB:[/bold] {duckdb}")
    tables = write_duckdb(parquet, duckdb)
    for t in tables:
        console.print(f"  [green][OK][/green] {t}")
    console.print(f"[green]Export done -> {duckdb}[/green]")


# ---------------------------------------------------------------------------
# visualize
# ---------------------------------------------------------------------------

@app.command("visualize")
def cmd_visualize(
    parquet: Path = typer.Option(..., "--parquet", help="Parquet base directory."),
    out: Path = typer.Option(..., "--out", help="Output directory for reports/figures."),
) -> None:
    """Produce PNG figures and HTML report from processed Parquet."""
    if not parquet.exists():
        console.print(f"[red]Parquet directory not found: {parquet}[/red]")
        raise typer.Exit(1)

    out.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.parquet_dir = parquet
    cfg.figures_dir = out / "figures"
    cfg.reports_dir = out

    console.print(f"[bold]Generating figures -> {cfg.figures_dir}[/bold]")
    run_visualize(cfg)
    console.print(f"[green]Visualize done -> {out}[/green]")


# ---------------------------------------------------------------------------
# run-all
# ---------------------------------------------------------------------------

@app.command("run-all")
def cmd_run_all(
    input: Path = typer.Option(..., "--input", help="Path to raw M1 CSV file."),
    out: Path = typer.Option(..., "--out", help="Output base directory."),
) -> None:
    """Run the full pipeline: clean -> resample -> export -> visualize."""
    out.mkdir(parents=True, exist_ok=True)
    interim_dir = out.parent / "interim" if out.name == "processed" else out / "interim"
    interim_dir.mkdir(parents=True, exist_ok=True)

    console.rule("[bold]Step 1/4 -- Clean[/bold]")
    # Try to run Agent 1's clean script
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    clean_script = project_root / "scripts" / "02_clean.py"
    if clean_script.exists():
        import subprocess
        result = subprocess.run(
            [sys.executable, str(clean_script),
             "--input", str(input), "--out", str(interim_dir)],
            capture_output=False,
        )
        if result.returncode != 0:
            console.print("[yellow]Clean script exited with non-zero code. Continuing...[/yellow]")
    else:
        console.print(
            "[yellow]scripts/02_clean.py not found (Agent 1 not done yet). "
            "Expecting pre-built interim Parquet.[/yellow]"
        )

    console.rule("[bold]Step 2/4 -- Resample[/bold]")
    cfg = Config()
    cfg.raw_csv = input
    cfg.interim_dir = interim_dir
    cfg.processed_dir = out
    cfg.parquet_dir = out / "parquet"
    cfg.duckdb_file = out / "xauusd.duckdb"
    cfg.reports_dir = project_root / "reports"
    cfg.figures_dir = project_root / "reports" / "figures"

    row_counts = run_resample(cfg)

    console.rule("[bold]Step 3/4 -- Export DuckDB[/bold]")
    write_duckdb(cfg.parquet_dir, cfg.duckdb_file)

    console.rule("[bold]Step 4/4 -- Visualize[/bold]")
    run_visualize(cfg, row_counts)

    console.rule("[bold]Done[/bold]")
    console.print(f"[green]All outputs in {out}[/green]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point registered via pyproject.toml [project.scripts]."""
    app()


if __name__ == "__main__":
    main()
