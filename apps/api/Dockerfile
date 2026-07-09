FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    TORCH_HOME=/app/.cache/torch \
    XDG_CACHE_HOME=/app/.cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip

COPY pyproject.toml ./
COPY music_assistant ./music_assistant

RUN pip install -e ".[vertexai]"

RUN mkdir -p /app/outputs /app/uploads /app/.cache/torch

EXPOSE 8000

CMD ["uvicorn", "music_assistant.interfaces.api:app", "--host", "0.0.0.0", "--port", "8000"]
