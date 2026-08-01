# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=python:3.12-slim
ARG PYTHON_VERSION=3.12
ARG FIND_BUILD_PROFILE=no-ai
ARG UV_SYNC_EXTRAS=""
FROM ${BASE_IMAGE}
ARG PYTHON_VERSION=3.12
ARG FIND_BUILD_PROFILE=no-ai
ARG UV_SYNC_EXTRAS=""

# Install system dependencies.
#
# The selected build profile controls this layer. CPU and NVIDIA artifacts need
# native build/OpenCV runtime libraries; no-AI and mock artifacts intentionally
# stay on the minimal Python base and never install those dependencies.
#
# So we branch: full set for ML, just curl (needed to fetch uv) for light.
RUN set -eux; \
    apt-get update; \
    if [ "${FIND_BUILD_PROFILE}" = "cpu" ] || [ "${FIND_BUILD_PROFILE}" = "nvidia" ]; then \
      apt-get install -y --no-install-recommends \
        python3 python3-dev build-essential libpq-dev \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 curl; \
    else \
      apt-get install -y --no-install-recommends curl; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# Ensure "python" command exists when base image only provides python3
RUN if ! command -v python >/dev/null 2>&1; then \
      ln -s /usr/bin/python3 /usr/bin/python; \
    fi

# Install uv into a stable system path. The installer writes to /root/.local/bin
# by default, so copy the binaries into /usr/local/bin for later build steps.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv \
    && install -m 0755 /root/.local/bin/uvx /usr/local/bin/uvx
ENV UV_PROJECT_ENVIRONMENT="/opt/find/.venv"
ENV UV_PYTHON="${PYTHON_VERSION}"
ENV UV_LINK_MODE="copy"
ENV PATH="/opt/find/.venv/bin:/usr/local/bin:/root/.local/bin:/root/.cargo/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV FIND_BUILD_PROFILE="${FIND_BUILD_PROFILE}"

# Set working directory
WORKDIR /app

# Copy project dependency metadata first for better caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies with uv. Keep uv's package cache in a BuildKit
# cache mount so it speeds rebuilds without bloating the final runtime image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project ${UV_SYNC_EXTRAS}

# Copy application code
COPY . .

# Install only the local package after source is available. Dependencies were
# already synced from pyproject.toml/uv.lock above, so source-only changes should
# not force uv to re-resolve the full ML environment on every rebuild.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps .

# Create directories for model cache
RUN mkdir -p /root/.cache/torch/hub/checkpoints \
    && mkdir -p /root/.cache/clip \
    && mkdir -p /root/.cache/huggingface

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "find_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
