ARG BASE_IMAGE=nvidia/cuda:12.1.1-runtime-ubuntu22.04
FROM ${BASE_IMAGE}

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    python3-pip \
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

# Install uv and ensure binary directory on PATH
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with uv (CUDA-enabled PyTorch) or regular pip
RUN if command -v uv >/dev/null 2>&1; then \
            uv pip install --system --no-cache -r requirements.txt; \
        else \
            pip install --no-cache-dir -r requirements.txt; \
        fi

# Copy application code
COPY . .

# Create directories for model cache
RUN mkdir -p /root/.cache/torch/hub/checkpoints \
    && mkdir -p /root/.cache/clip \
    && mkdir -p /root/.cache/huggingface

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
