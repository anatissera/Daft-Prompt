FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m pip install --upgrade pip

COPY pyproject.toml ./
COPY llm_band ./llm_band

RUN pip install -e .

RUN mkdir -p /app/outputs

EXPOSE 8000

CMD ["uvicorn", "llm_band.api:app", "--host", "0.0.0.0", "--port", "8000"]
