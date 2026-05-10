# ---------------------------------------------------------------------------
# Makefile — Time Series Data Preparation
# Targets work in Linux/macOS and Git Bash / WSL on Windows.
# Native Windows users: see tasks.ps1 for PowerShell equivalents.
# ---------------------------------------------------------------------------

PYTHON   ?= python
PIP      ?= pip
SRC      ?= src
TESTS    ?= tests
INPUT    ?= data/raw/XAUUSD_M1.csv
OUT      ?= data/processed

.PHONY: install lint format test clean-data run docker-build docker-run help

## install  — create venv and install all dev dependencies
install:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

## lint     — run ruff check + mypy
lint:
	ruff check $(SRC) $(TESTS) scripts
	mypy $(SRC)/tsdataprep

## format   — auto-fix ruff lint issues and sort imports
format:
	ruff check --fix $(SRC) $(TESTS) scripts
	ruff format $(SRC) $(TESTS) scripts

## test     — run pytest with coverage
test:
	pytest --cov=$(SRC)/tsdataprep --cov-report=term-missing -q $(TESTS)

## clean-data — remove generated data outputs (keeps raw source)
clean-data:
	rm -rf data/interim/* data/processed/*
	rm -rf reports/figures/*.png reports/*.html reports/*.json

## run      — run the full pipeline locally
run:
	tsdataprep run-all --input $(INPUT) --out $(OUT)

## docker-build — build the Docker image
docker-build:
	docker build -t tsdataprep:latest .

## docker-run — run the full pipeline inside Docker
docker-run:
	docker compose up etl

## help     — list available targets
help:
	@grep -E '^## ' Makefile | sed 's/^## //'
