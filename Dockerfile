# Multi-purpose image — used for both `backend` and `scheduler` services.
# Same code, different command.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# System dependencies
#   build-essential + libpq-dev → asyncpg, grpcio compile if needed
#   curl                       → HEALTHCHECK
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# uv for fast deterministic installs from uv.lock
RUN pip install --no-cache-dir "uv>=0.4"

# ── Dependency layer (cacheable) ────────────────────────────────────────────────
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Application code ────────────────────────────────────────────────────────────
COPY backend ./backend
COPY agents ./agents
COPY mcp_server ./mcp_server
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Install the project itself (so `python -m agents.scheduler` etc. resolve)
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Run as non-root
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

# Healthcheck checks the FastAPI service.
# The scheduler container overrides CMD and ignores this (its docker-compose
# entry sets a different healthcheck, or none).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fs http://localhost:8001/health || exit 1

# Default command — run the FastAPI backend.
# Scheduler service overrides this with `python -m agents.scheduler`.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
