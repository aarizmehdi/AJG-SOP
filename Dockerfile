FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency specification first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev group)
RUN uv sync --python 3.12 --locked --no-dev --no-install-project

# Copy application source (monorepo layout)
COPY apps/ apps/
COPY services/ services/
COPY packages/ packages/
COPY scripts/ scripts/

# Railway injects PORT; default to 8000 for local testing
ENV PORT=8000

EXPOSE ${PORT}

# Production ASGI server — single worker, no reload, bind to 0.0.0.0
CMD ["sh", "-c", "uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS:-1} --log-level info --timeout-keep-alive 30"]
