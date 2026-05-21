# syntax=docker/dockerfile:1.7

# Multi-stage Dockerfile for meow-bot (spec §15.1).
#
# - `base` resolves and installs the Python environment from uv.lock so both
#   final targets share the same cached layer.
# - `receiver` runs the FastAPI app behind uvicorn.
# - `worker` runs the durable worker process.
#
# Build:
#   docker build --target receiver -t meow-receiver .
#   docker build --target worker   -t meow-worker   .

ARG PYTHON_VERSION=3.13
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.9.7

############################
# Stage: uv (alias for the uv binary image, lets us interpolate ARG)
############################
FROM ${UV_IMAGE} AS uv

############################
# Stage: base
############################
FROM python:${PYTHON_VERSION}-slim AS base

# Bring in the uv binary from the aliased stage. Pinning UV_IMAGE keeps builds
# reproducible across rebuilds.
COPY --from=uv /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Install dependencies first (without the project itself) so the layer is
# reused as long as pyproject.toml + uv.lock are unchanged.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy the source tree and install the project into the locked environment.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

############################
# Target: receiver
############################
FROM base AS receiver

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "meow.receiver.app:app", "--host", "0.0.0.0", "--port", "8000"]

############################
# Target: worker
############################
FROM base AS worker

CMD ["uv", "run", "python", "-m", "meow.worker"]
