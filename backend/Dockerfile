# Build from the repository root:  docker build -f backend/Dockerfile .
# Two stages: "build" installs dependencies with uv; the final image only gets the result.

# ---------- Stage 1: build ----------
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first: this layer is cached until pyproject.toml or uv.lock changes.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Then our own code, installed into the venv as a normal package.
COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

# ---------- Stage 2: runtime ----------
FROM python:3.14-slim
# Never run as root inside the container.
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY contract/openapi.yaml /app/contract/openapi.yaml
# Alembic reads its settings from pyproject.toml; the "migrate" service runs these.
COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/migrations /app/migrations

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HINDSIGHT_CONTRACT_PATH=/app/contract/openapi.yaml

USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

# No --reload here: this is the "production" run configuration.
CMD ["uvicorn", "hindsight.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
