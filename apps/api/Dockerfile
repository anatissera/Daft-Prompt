FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    TORCH_HOME=/app/.cache/torch \
    XDG_CACHE_HOME=/app/.cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip

COPY pyproject.toml ./

# Heavy, slow-moving layer: keyed on pyproject.toml alone so editing application
# code never re-downloads torch or the Demucs weights.
#
# torch comes from PyTorch's CPU index because Demucs runs on CPU here — the
# default PyPI wheels drag in ~4.5 GB of unused CUDA/triton libraries. Installing
# it first means the later `pip install -e .` sees the requirement satisfied and
# leaves it alone.
#
# numpy is explicit because demucs imports it without declaring it, relying on
# the default torch wheels to pull it in — the CPU wheels don't.
#
# The htdemucs checkpoint is fetched at build time: on an ephemeral filesystem
# (Cloud Run) a lazy first-request download would repeat on every cold start.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.5,<2.6" "torchaudio>=2.5,<2.6" \
    && pip install "demucs>=4.0" "numpy<3" \
    && python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

COPY music_assistant ./music_assistant

# All three provider extras: the LLM fallback chain (LLM_FALLBACK_PROVIDERS)
# skips any provider whose package is missing, so a partial install would
# silently shorten the chain.
RUN pip install -e ".[gemini,groq,openrouter]"

RUN mkdir -p /app/outputs /app/uploads /app/.cache/torch

EXPOSE 8000

# Goes through sh so ${PORT} expands — Cloud Run injects it, local and
# docker-compose fall back to 8000 — while `exec` keeps uvicorn as PID 1 so it
# still receives SIGTERM on shutdown. Artifact and upload roots stay at their
# in-repo defaults here; ARTIFACTS_DIR and REFERENCE_UPLOAD_DIR override them on
# hosts with a read-only or memory-backed filesystem.
CMD ["sh", "-c", "exec uvicorn music_assistant.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
