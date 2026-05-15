ARG PYTHON_VERSION=3.12
ARG BASE_IMAGE_RUNTIME=python:3.12-slim
ARG BASE_IMAGE_GPU=nvidia/cuda:12.1.1-runtime-ubuntu22.04

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: base-runtime
# Minimal Debian-based Python 3.12 image for the API server and mock worker.
# python:3.12-slim ships Python 3.12 at /usr/local/bin/python3.12.
# No additional apt packages are needed for the core API runtime.
# ─────────────────────────────────────────────────────────────────────────────
FROM ${BASE_IMAGE_RUNTIME} AS base-runtime
RUN ln -sf /usr/local/bin/python3.12 /usr/bin/python3.12 && \
    ln -sf /usr/local/bin/python3 /usr/bin/python3 && \
    ln -sf /usr/local/bin/python /usr/bin/python

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: base-gpu
# nvidia/cuda Ubuntu 22.04 base with Python 3.12 installed from the
# deadsnakes PPA.  Ubuntu 22.04 only ships Python 3.10 in its default
# repos; deadsnakes provides 3.12 at /usr/bin/python3.12.
# Both builder-ml and worker-ml-gpu derive from this stage, so the Python
# binary path is identical in both — the key requirement for a portable venv.
# ─────────────────────────────────────────────────────────────────────────────
FROM ${BASE_IMAGE_GPU} AS base-gpu
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev \
        libpq-dev \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: builder-core
# Installs ONLY the core API dependencies (FastAPI, SQLAlchemy, MinIO, etc.)
# into /opt/find/.venv using the system Python from python:3.12-slim.
#
# UV_PYTHON_PREFERENCE=only-system forces uv to use /usr/local/bin/python3.12
# instead of downloading its own managed interpreter.  This is critical:
# the .venv's shebang lines embed this path, so it MUST exist in the final
# runtime image too (which it does, since both stages share python:3.12-slim).
#
# UV_PROJECT_ENVIRONMENT tells uv to place the venv at /opt/find/.venv
# (outside /app) so the bind-mount in docker-compose doesn't shadow it.
# ─────────────────────────────────────────────────────────────────────────────
FROM base-runtime AS builder-core
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
ENV UV_PYTHON_PREFERENCE=only-system
ENV UV_PROJECT_ENVIRONMENT="/opt/find/.venv"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --no-cache

# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: builder-ml
# Installs the FULL ML stack (Torch+CUDA, Transformers, PaddleOCR, YOLO …)
# into /opt/find/.venv using Python 3.12 from the deadsnakes PPA.
#
# UV_PYTHON_PREFERENCE=only-system now works because base-gpu provides
# Python 3.12 at /usr/bin/python3.12.  The resulting .venv shebangs embed
# /usr/bin/python3.12, which also exists in the worker-ml-gpu final stage
# (they share the same base-gpu layer), so the venv is fully portable.
#
# build-essential is added here (builder stage only) for packages like
# insightface that require C++ compilation — it is NOT in the final image.
# ─────────────────────────────────────────────────────────────────────────────
FROM base-gpu AS builder-ml
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
ENV UV_PYTHON_PREFERENCE=only-system
ENV UV_PROJECT_ENVIRONMENT="/opt/find/.venv"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --extra ml --no-cache

# ─────────────────────────────────────────────────────────────────────────────
# Stage 5 (target: api)
# Final API image — no ML libraries, no build tools, no GPU runtime.
# Copies only the pre-built core venv from builder-core.
# ─────────────────────────────────────────────────────────────────────────────
FROM base-runtime AS api
WORKDIR /app
COPY --from=builder-core /opt/find/.venv /opt/find/.venv
ENV PATH="/opt/find/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "find_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 6 (target: worker-mock)
# Same slim image as the API but runs the RQ worker process in mock ML mode.
# Ideal for contributors without a GPU — builds in ~2 min, no torch.
# ─────────────────────────────────────────────────────────────────────────────
FROM base-runtime AS worker-mock
WORKDIR /app
COPY --from=builder-core /opt/find/.venv /opt/find/.venv
ENV PATH="/opt/find/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV ML_MODE=mock
COPY . .
CMD ["rq", "worker", "--url", "redis://redis:6379", "high", "default", "low"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 7 (target: worker-ml-cpu)
# CPU-only ML worker.  Uses the full ML venv from builder-ml but runs on
# the slim python:3.12-slim base (no CUDA overhead).
# NOTE: Python paths differ between builder-ml (/usr/bin/python3.12) and
# base-runtime (/usr/local/bin/python3.12), so we rely on `python -m rq`
# via the CMD / compose override to bypass any shebang path mismatch.
# ─────────────────────────────────────────────────────────────────────────────
FROM base-runtime AS worker-ml-cpu
WORKDIR /app
COPY --from=builder-ml /opt/find/.venv /opt/find/.venv
ENV PATH="/opt/find/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
COPY . .
CMD ["rq", "worker", "--url", "redis://redis:6379", "high", "default", "low"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 8 (target: worker-ml-gpu)
# Full production GPU ML worker.
# Copies the ML venv from builder-ml.  Both stages share base-gpu, so the
# Python 3.12 interpreter at /usr/bin/python3.12 exists in both — the venv
# shebangs resolve correctly without any path mismatch.
# ─────────────────────────────────────────────────────────────────────────────
FROM base-gpu AS worker-ml-gpu
WORKDIR /app
COPY --from=builder-ml /opt/find/.venv /opt/find/.venv
ENV PATH="/opt/find/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
COPY . .
CMD ["rq", "worker", "--url", "redis://redis:6379", "high", "default", "low"]
