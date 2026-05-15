ARG BASE_IMAGE=nvidia/cuda:12.1.1-runtime-ubuntu22.04
ARG PYTHON_VERSION=3.12
ARG UV_SYNC_EXTRAS="--extra ml"
FROM ${BASE_IMAGE}
ARG UV_SYNC_EXTRAS="--extra ml"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Ensure "python" command exists when base image only provides python3
RUN if ! command -v python >/dev/null 2>&1; then \
      ln -s /usr/bin/python3 /usr/bin/python; \
    fi

# Install uv and ensure binary directory on PATH. Keep the project venv
# outside /app so the docker-compose bind mount cannot hide it at runtime.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV UV_PROJECT_ENVIRONMENT="/opt/find/.venv"
ENV UV_PYTHON="${PYTHON_VERSION}"
ENV PATH="/opt/find/.venv/bin:/root/.local/bin:/root/.cargo/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Set working directory
WORKDIR /app

# Copy project dependency metadata first for better caching
COPY pyproject.toml uv.lock ./

# Install Python dependencies with uv
RUN uv sync --no-dev --no-install-project ${UV_SYNC_EXTRAS}

# Copy application code
COPY . .

# Install the local package after source is available.
RUN uv sync --no-dev ${UV_SYNC_EXTRAS}

# Create directories for model cache
RUN mkdir -p /root/.cache/torch/hub/checkpoints \
    && mkdir -p /root/.cache/clip \
    && mkdir -p /root/.cache/huggingface

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "find_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
