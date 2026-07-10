# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    TORCH_HOME=/app/.cache/torch \
    XDG_CACHE_HOME=/app/.cache

WORKDIR /app

ARG INSTALL_AUDIO_SYSTEM_DEPS="false"
RUN if [ "$INSTALL_AUDIO_SYSTEM_DEPS" = "true" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ffmpeg build-essential \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN python -m pip install --upgrade pip

# Install dependencies before copying source so application edits can reuse the
# expensive Torch/MIR/provider layer. pyproject.toml remains the only dependency
# manifest; the helper simply selects the Docker runtime's Vertex extra.
COPY pyproject.toml ./
COPY scripts/install_runtime_deps.py ./install_runtime_deps.py
ARG RUNTIME_EXTRAS="vertexai"
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_NO_CACHE_DIR=0 python install_runtime_deps.py $RUNTIME_EXTRAS

COPY music_assistant ./music_assistant
RUN pip install --no-deps -e .

RUN mkdir -p /app/outputs /app/uploads /app/.cache/torch

EXPOSE 8000

CMD ["uvicorn", "music_assistant.interfaces.api:app", "--host", "0.0.0.0", "--port", "8000"]
