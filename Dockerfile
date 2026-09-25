# CUDA 12.4 runtime — driver 580.x is backward-compatible with this toolkit version.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY README.md ./
COPY config ./config

RUN uv sync --extra hf --extra cuda

ENTRYPOINT ["uv", "run", "--active", "python", "-m", "fine_tuning_experimentations.hf_mps.train"]
CMD ["--config-dir=config", "--config-name=train_cuda"]