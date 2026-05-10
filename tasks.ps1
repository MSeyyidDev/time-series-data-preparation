<#
.SYNOPSIS
    PowerShell task runner — native Windows equivalent of the Makefile.
    Run: .\tasks.ps1 <target>

.EXAMPLE
    .\tasks.ps1 install
    .\tasks.ps1 lint
    .\tasks.ps1 test
    .\tasks.ps1 run
    .\tasks.ps1 docker-build
    .\tasks.ps1 docker-run
#>

param(
    [Parameter(Position = 0, Mandatory = $false)]
    [ValidateSet('install', 'lint', 'format', 'test', 'clean-data', 'run', 'docker-build', 'docker-run', 'help')]
    [string]$Target = 'help'
)

$ErrorActionPreference = 'Stop'

$INPUT_FILE = 'data\raw\XAUUSD_M1.csv'
$OUT_DIR    = 'data\processed'
$SRC        = 'src'
$TESTS      = 'tests'

function Invoke-Install {
    Write-Host "==> Installing dependencies..." -ForegroundColor Cyan
    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"
}

function Invoke-Lint {
    Write-Host "==> Running ruff check..." -ForegroundColor Cyan
    ruff check $SRC $TESTS scripts
    Write-Host "==> Running mypy..." -ForegroundColor Cyan
    mypy "$SRC\tsdataprep"
}

function Invoke-Format {
    Write-Host "==> Auto-fixing ruff issues..." -ForegroundColor Cyan
    ruff check --fix $SRC $TESTS scripts
    ruff format $SRC $TESTS scripts
}

function Invoke-Test {
    Write-Host "==> Running pytest with coverage..." -ForegroundColor Cyan
    pytest --cov="$SRC\tsdataprep" --cov-report=term-missing -q $TESTS
}

function Invoke-CleanData {
    Write-Host "==> Removing generated outputs..." -ForegroundColor Cyan
    if (Test-Path "data\interim") { Get-ChildItem "data\interim" -Recurse | Remove-Item -Force -Recurse }
    if (Test-Path "data\processed") { Get-ChildItem "data\processed" -Recurse | Remove-Item -Force -Recurse }
    if (Test-Path "reports\figures") { Get-ChildItem "reports\figures" -Filter "*.png" | Remove-Item -Force }
    Write-Host "Clean complete." -ForegroundColor Green
}

function Invoke-Run {
    Write-Host "==> Running full pipeline..." -ForegroundColor Cyan
    tsdataprep run-all --input $INPUT_FILE --out $OUT_DIR
}

function Invoke-DockerBuild {
    Write-Host "==> Building Docker image..." -ForegroundColor Cyan
    docker build -t tsdataprep:latest .
}

function Invoke-DockerRun {
    Write-Host "==> Running pipeline in Docker..." -ForegroundColor Cyan
    docker compose up etl
}

function Show-Help {
    Write-Host @"
Available targets:
  install      Install all dev dependencies (pip install -e .[dev])
  lint         Run ruff check + mypy
  format       Auto-fix ruff issues and sort imports
  test         Run pytest with coverage
  clean-data   Remove generated data outputs
  run          Run the full pipeline locally
  docker-build Build the Docker image
  docker-run   Run the full pipeline inside Docker
  help         Show this help message
"@
}

switch ($Target) {
    'install'      { Invoke-Install }
    'lint'         { Invoke-Lint }
    'format'       { Invoke-Format }
    'test'         { Invoke-Test }
    'clean-data'   { Invoke-CleanData }
    'run'          { Invoke-Run }
    'docker-build' { Invoke-DockerBuild }
    'docker-run'   { Invoke-DockerRun }
    default        { Show-Help }
}
