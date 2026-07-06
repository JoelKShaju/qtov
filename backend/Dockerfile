FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY app ./app
# Include the observability extra so OTLP tracing works when enabled.
RUN pip install --upgrade pip && pip install ".[observability]"

# Source is bind-mounted in dev (docker compose); baked into the image for prod.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
