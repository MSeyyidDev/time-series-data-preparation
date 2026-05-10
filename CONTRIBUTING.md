# Contributing

Thank you for your interest in contributing to Time Series Data Preparation.

## Setting up the development environment

**Requirements:** Python 3.11, Git, (optional) Docker.

```bash
# 1. Fork and clone
git clone https://github.com/seyyidsahin2834/time-series-data-preparation.git
cd time-series-data-preparation

# 2. Create a virtual environment
python -m venv .venv
# Linux / macOS / Git Bash
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

# 3. Install all development dependencies
pip install -e ".[dev]"

# 4. Verify everything works
pytest -q
ruff check src tests scripts
```

## Running tests

```bash
# All tests with coverage
pytest --cov=src/tsdataprep --cov-report=term-missing -q

# A single file
pytest tests/test_clean.py -v
```

## Code style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for issues
ruff check src tests scripts

# Auto-fix and format
ruff check --fix src tests scripts
ruff format src tests scripts
```

Line length is 100 characters. Follow existing module structure — one concern per module.

## Type annotations

All public functions must have full type annotations. We run mypy in lenient mode:

```bash
mypy src/tsdataprep --ignore-missing-imports
```

## Commit message style

Use the conventional-commits format:

```
feat: add parquet writer for W1 timeframe
fix: drop duplicate timestamps before OHLC sanity check
docs: update normalization rationale in docs/normalization.md
chore(deps): bump pyarrow to 16.0
```

## Pull requests

1. Branch from `develop`, not `main`.
2. One logical change per PR.
3. All CI checks must pass (ruff, mypy, pytest).
4. Update `docs/` if your change affects public behaviour or the data schema.

## What not to change

- `SHARED_SPEC.md` — frozen specification document.
- The canonical column schema defined in spec section 3.1.
- The CLI subcommand names defined in spec section 7.

If you believe the spec needs updating, open an issue first for discussion.
