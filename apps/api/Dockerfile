FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN python -m pip install --upgrade pip

COPY pyproject.toml ./
COPY music_assistant ./music_assistant

RUN pip install -e .

RUN mkdir -p /app/outputs

EXPOSE 8000

CMD ["uvicorn", "music_assistant.api:app", "--host", "0.0.0.0", "--port", "8000"]
