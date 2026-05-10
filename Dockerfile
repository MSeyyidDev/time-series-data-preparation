# ---------------------------------------------------------------------------
# Time Series Data Preparation
# Python 3.11-slim, non-root user, installs only runtime deps.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

# System dependencies needed by pyarrow / matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install Python dependencies (as root so they land in system site-packages)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy package source
COPY src/ ./src/
COPY pyproject.toml ./

# Install the package itself (editable not needed in production)
RUN pip install --no-cache-dir --no-deps .

# Data volume mount point — populated at runtime
RUN mkdir -p /app/data/raw /app/data/interim /app/data/processed /app/reports/figures \
    && chown -R appuser:appgroup /app

USER appuser

# Smoke-test that the CLI is importable
RUN tsdataprep --help

CMD ["tsdataprep", "--help"]
